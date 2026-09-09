"""Read-only Dropbox integration. OAuth credentials never leave the server."""
import base64
import hashlib
import json
import os
import secrets
import threading
import time
from pathlib import Path
from urllib.parse import urlencode
import httpx
from .settings import settings
from .database import get_db_connection
from .scanner import VALID_EXTENSIONS


class StorageError(Exception):
    def __init__(self, message, status=503):
        super().__init__(message)
        self.status = status


class Dropbox:
    def __init__(self):
        self.lock = threading.RLock()
        self.access_token = None
        self.expires_at = 0
        self.pending = None

    def credentials(self):
        path = settings.DROPBOX_CREDENTIALS_PATH
        return json.loads(path.read_text()) if path.is_file() else None

    def status(self):
        creds = self.credentials()
        return {"connected": bool(creds), "folder": creds["folder"] if creds else None}

    def begin(self, app_key, folder):
        with self.lock:
            if self.credentials():
                raise StorageError("Dropbox is already connected. Changing accounts requires an explicit migration.", 409)
            verifier = secrets.token_urlsafe(64)
            flow_id = secrets.token_hex(24)
            self.pending = {"app_key": app_key, "folder": folder, "verifier": verifier,
                            "expires": time.time() + 600, "flow_id": flow_id}
            challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
            return {"flow_id": flow_id, "authorize_url": "https://www.dropbox.com/oauth2/authorize?" + urlencode({
                "client_id": app_key, "response_type": "code", "token_access_type": "offline",
                "code_challenge": challenge, "code_challenge_method": "S256",
                "scope": "account_info.read files.metadata.read files.content.read", "state": flow_id})}

    def finish(self, flow_id, code):
        with self.lock:
            pending = self.pending
            if not pending or pending["expires"] < time.time() or not secrets.compare_digest(pending["flow_id"], flow_id):
                raise StorageError("Connection attempt expired; start again", 400)
            with httpx.Client(timeout=30) as client:
                result = client.post("https://api.dropboxapi.com/oauth2/token", data={
                    "grant_type": "authorization_code", "code": code, "client_id": pending["app_key"],
                    "code_verifier": pending["verifier"]})
            if result.status_code != 200 or not result.json().get("refresh_token"):
                raise StorageError("Dropbox rejected the code. Check the app permissions and start again.", 400)
            data = result.json()
            with httpx.Client(timeout=30) as client:
                account = client.post('https://api.dropboxapi.com/2/users/get_current_account',
                                      headers={'Authorization': f"Bearer {data['access_token']}"})
            if account.status_code != 200:
                raise StorageError('Enable account_info.read and start connection again', 400)
            root_namespace = account.json()['root_info']['root_namespace_id']
            path = settings.DROPBOX_CREDENTIALS_PATH
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            payload = {"app_key": pending["app_key"], "folder": pending["folder"],
                       "refresh_token": data["refresh_token"], "account_id": data.get("account_id"),
                       "root_namespace_id": root_namespace}
            # Atomic replacement, restrictive permissions from creation (including temporary file).
            temp = path.with_suffix(".tmp")
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as stream:
                json.dump(payload, stream)
                stream.flush()
                os.fsync(stream.fileno())
            temp.replace(path)
            self.pending = None
            self.access_token = None
            return self.status()

    def token(self):
        with self.lock:
            if self.access_token and self.expires_at > time.time() + 60:
                return self.access_token
            creds = self.credentials()
            if not creds:
                raise StorageError("Connect Dropbox in Settings first")
            with httpx.Client(timeout=30) as client:
                result = client.post("https://api.dropboxapi.com/oauth2/token", data={
                    "grant_type": "refresh_token", "refresh_token": creds["refresh_token"], "client_id": creds["app_key"]})
            if result.status_code != 200:
                raise StorageError("Dropbox authorization needs attention (token refresh failed)")
            data = result.json()
            self.access_token = data["access_token"]
            self.expires_at = time.time() + data["expires_in"]
            return self.access_token

    def rpc(self, method, args):
        with httpx.Client(timeout=60) as client:
            response = client.post(f"https://api.dropboxapi.com/2/{method}", json=args,
                                   headers=self.headers())
        if response.status_code != 200:
            if response.status_code == 409 and response.json().get("error", {}).get(".tag") == "reset":
                raise StorageError("cursor_reset", 409)
            raise StorageError(f"Dropbox {method} failed (HTTP {response.status_code}); check folder, authorization, or rate limits")
        return response.json()

    def headers(self):
        headers = {'Authorization': f'Bearer {self.token()}'}
        namespace = self.credentials().get('root_namespace_id')
        if namespace:
            headers['Dropbox-API-Path-Root'] = json.dumps({'.tag': 'root', 'root': namespace})
        return headers

    def changes(self, cursor=None):
        creds = self.credentials()
        if not creds:
            raise StorageError("Connect Dropbox in Settings first")
        full = not cursor
        try:
            page = self.rpc("files/list_folder/continue", {"cursor": cursor}) if cursor else self.rpc(
                "files/list_folder", {"path": creds["folder"], "recursive": True, "include_deleted": True})
        except StorageError as exc:
            if str(exc) != "cursor_reset":
                raise
            full = True
            page = self.rpc("files/list_folder", {"path": creds["folder"], "recursive": True, "include_deleted": True})
        entries = list(page["entries"])
        while page["has_more"]:
            page = self.rpc("files/list_folder/continue", {"cursor": page["cursor"]})
            entries.extend(page["entries"])
        return entries, page["cursor"], full

    def download(self, reel, write):
        # Exact revision, not current path. Size and Dropbox's block hash are checked by the cache.
        # Dropbox rejects the deprecated separate `rev` argument. A revision path
        # selects immutable content; validate the returned file ID as well below.
        args = json.dumps({"path": f"rev:{reel['source_version']}"})
        with httpx.Client(timeout=httpx.Timeout(60, connect=15)) as client:
            with client.stream("POST", "https://content.dropboxapi.com/2/files/download",
                               headers={**self.headers(), "Dropbox-API-Arg": args}) as response:
                if response.status_code != 200:
                    raise StorageError(f"Dropbox download failed (HTTP {response.status_code}); refresh the catalog and retry")
                metadata = json.loads(response.headers.get("Dropbox-API-Result", "{}"))
                if metadata.get("rev") != reel["source_version"] or metadata.get("id") != reel["provider_id"]:
                    raise StorageError("Dropbox returned a different file revision", 409)
                for chunk in response.iter_bytes(256 * 1024):
                    write(chunk)


dropbox = Dropbox()


def sync_dropbox():
    from .archive import now as now_iso
    # Reconcile a fresh recursive metadata snapshot on manual and periodic scans.
    # A cursor-only scan cannot repair previously missed paths/tombstones. This
    # also reconciles entire moved folders without downloading any original media.
    entries, cursor, full = dropbox.changes(None)
    now = now_iso()
    stats = dict(scanned=0, added=0, updated=0, moved=0, missing=0, skipped=0)
    # No cursor advancement or missing-file reconciliation until every page succeeds.
    with get_db_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if full:
            conn.execute("UPDATE reels SET storage_status='missing' WHERE storage_provider='dropbox'")
        for entry in entries:
            path = entry.get("path_lower", "")
            if entry[".tag"] == "deleted":
                # Escape LIKE metacharacters in real folder names.
                prefix = path.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "/%"
                conn.execute("UPDATE reels SET storage_status='missing' WHERE storage_provider='dropbox' AND (provider_path=? OR provider_path LIKE ? ESCAPE '\\')", (path, prefix))
                continue
            if entry[".tag"] != "file" or Path(entry["name"]).suffix.lower() not in VALID_EXTENSIONS:
                continue
            stats["scanned"] += 1
            old = conn.execute("SELECT * FROM reels WHERE storage_provider='dropbox' AND provider_id=?", (entry["id"],)).fetchone()
            virtual_path = 'dropbox:' + entry.get('path_display', path)
            # A replacement at the same path is a NEW identity. Retain the old editorial record.
            conn.execute("UPDATE reels SET filepath='dropbox-missing:'||provider_id,storage_status='missing' WHERE filepath=? AND provider_id!=?", (virtual_path, entry['id']))
            values = (entry["name"], virtual_path, Path(entry["name"]).suffix.lower(),
                      entry["size"], entry["server_modified"], now, entry["rev"], path, entry.get("content_hash"))
            if old:
                if old['filepath'] != virtual_path:
                    stats['moved'] += 1
                conn.execute("""UPDATE reels SET filename=?,filepath=?,file_extension=?,file_size=?,created_at=?,last_seen_at=?,
                    source_version=?,provider_path=?,content_hash=?,storage_status='cloud' WHERE id=?""", (*values, old["id"]))
                if old["source_version"] != entry["rev"]:
                    conn.execute("""UPDATE reels SET thumbnail_path=NULL,duration_seconds=0,quick_summary=NULL,quick_tags=NULL,
                        quick_category=NULL,quick_summary_at=NULL,quick_summary_source=NULL,quick_summary_model=NULL,
                        approved=0,status=CASE WHEN status='ready' THEN 'needs_review' ELSE status END WHERE id=?""", (old["id"],))
                    conn.execute("DELETE FROM summary_jobs WHERE reel_id=? AND status!='processing'", (old["id"],))
                stats["updated"] += 1
            else:
                conn.execute("""INSERT INTO reels(filename,filepath,file_extension,file_size,created_at,last_seen_at,source_version,
                    provider_path,content_hash,storage_provider,provider_id,duration_seconds,updated_at,discovered_at,storage_status)
                    VALUES (?,?,?,?,?,?,?,?,?,'dropbox',?,0,?,?,'cloud')""", (*values, entry["id"], now, now))
                stats["added"] += 1
        stats["missing"] = conn.execute("SELECT count(*) FROM reels WHERE storage_provider='dropbox' AND storage_status='missing'").fetchone()[0]
        conn.execute("INSERT OR REPLACE INTO archive_state(key,value) VALUES ('dropbox_cursor',?)", (json.dumps(cursor),))
        conn.commit()
    return stats
