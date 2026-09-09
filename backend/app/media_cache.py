"""Single-process cache with strict byte reservations, LRU/TTL eviction and reader pins.

The hosting process holds an exclusive OS lock. Five concurrent downloads share a
single reservation ledger; partial files count at their FULL expected size.
"""
import fcntl
import hashlib
import shutil
import re
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from .database import get_db_connection
from .dropbox_storage import dropbox, StorageError
from .settings import settings


class DropboxHash:
    def __init__(self):
        self.outer = hashlib.sha256()
        self.block = hashlib.sha256()
        self.length = 0

    def update(self, data):
        while data:
            count = min(len(data), 4 * 1024 * 1024 - self.length)
            self.block.update(data[:count])
            self.length += count
            data = data[count:]
            if self.length == 4 * 1024 * 1024:
                self.outer.update(self.block.digest())
                self.block = hashlib.sha256()
                self.length = 0

    def hexdigest(self):
        result = self.outer.copy()
        if self.length:
            result.update(self.block.digest())
        return result.hexdigest()


def cache_key(reel):
    return hashlib.sha256(f"{reel['provider_id']}:{reel['source_version']}".encode()).hexdigest()


class MediaCache:
    def __init__(self):
        self.lock = threading.RLock()
        self.downloads = threading.BoundedSemaphore(settings.MAX_CONCURRENT_DOWNLOADS)
        self.key_locks = {}
        self.pins = {}
        self.reserved = {}
        self.auxiliary_reserved = 0  # Space promised to the serial preview encoder.
        self.owner = None

    def start(self):
        with self.lock:
            if self.owner:
                return
            if settings.CACHE_FOLDER in {Path('/'), Path.home(), settings.DATABASE_PATH.parent.resolve(),
                                          settings.REELS_FOLDER.resolve(), settings.THUMBNAILS_FOLDER.resolve()}:
                raise RuntimeError('CACHE_FOLDER must be a dedicated cache directory, never an archive or data root')
            settings.CACHE_FOLDER.mkdir(parents=True, exist_ok=True)
            owner = (settings.CACHE_FOLDER / ".owner.lock").open("a")
            try:
                fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                owner.close()
                raise RuntimeError("Cache already in use. Run exactly one Uvicorn worker per database/cache.")
            self.owner = owner
            with get_db_connection() as conn:
                conn.execute("DELETE FROM cache_entries WHERE state!='ready'")
                ready = {r["key"] for r in conn.execute("SELECT key FROM cache_entries")}
                # Only this dedicated cache's owned media files; never originals or arbitrary directories.
                for path in settings.CACHE_FOLDER.iterdir():
                    if re.fullmatch(r'[a-f0-9]{64}\.(part|media)', path.name) and (path.suffix == '.part' or path.stem not in ready):
                        path.unlink()
                for key in ready:
                    if not self.path(key).is_file():
                        conn.execute("DELETE FROM cache_entries WHERE key=?", (key,))
                conn.commit()
            try:
                self.cleanup()
            except StorageError:
                pass  # Keep the status/login UI available when the disk is low.

    def path(self, key):
        return settings.CACHE_FOLDER / (key + ".media")

    def _evict(self, conn, key):
        self.path(key).unlink(missing_ok=True)
        conn.execute("DELETE FROM cache_entries WHERE key=?", (key,))

    def cleanup(self, required=0):
        with self.lock, get_db_connection() as conn:
            used = conn.execute("SELECT COALESCE(SUM(size),0) FROM cache_entries").fetchone()[0]
            for row in conn.execute("SELECT * FROM cache_entries WHERE state='ready' ORDER BY accessed_at").fetchall():
                shortage = used + required > settings.CACHE_MAX_BYTES or (
                    shutil.disk_usage(settings.CACHE_FOLDER).free - sum(self.reserved.values()) - self.auxiliary_reserved - required < settings.MIN_FREE_DISK_BYTES)
                expired = row["accessed_at"] < time.time() - settings.CACHE_TTL_SECONDS
                if self.pins.get(row["key"], 0) or not (shortage or expired):
                    continue
                self._evict(conn, row["key"])
                used -= row["size"]
            conn.commit()
            if used + required > settings.CACHE_MAX_BYTES:
                raise StorageError("Cache is full of active files; retry after downloads/processing finish", 507)
            if shutil.disk_usage(settings.CACHE_FOLDER).free - sum(self.reserved.values()) - self.auxiliary_reserved - required < settings.MIN_FREE_DISK_BYTES:
                raise StorageError("Minimum free disk reserve reached; free VM space or adjust the configured reserve", 507)

    def acquire(self, reel):
        if reel.get("storage_status") == "missing":
            raise StorageError("Source file is missing; refresh the archive", 404)
        self.start()
        key = cache_key(reel)
        with self.lock:
            key_lock = self.key_locks.setdefault(key, threading.Lock())
        with key_lock:
            with self.lock, get_db_connection() as conn:
                ready = conn.execute("SELECT * FROM cache_entries WHERE key=? AND state='ready'", (key,)).fetchone()
                if ready and self.path(key).is_file():
                    self.pins[key] = self.pins.get(key, 0) + 1
                    conn.execute("UPDATE cache_entries SET accessed_at=? WHERE key=?", (time.time(), key))
                    conn.commit()
                    return self.path(key), key
            with self.downloads:
                size = reel["file_size"]
                if size <= 0 or size > settings.CACHE_MAX_BYTES:
                    raise StorageError("File is empty or exceeds the configured media cache budget", 413)
                with self.lock:
                    self.cleanup(required=size)
                    self.reserved[key] = size
                    with get_db_connection() as conn:
                        conn.execute("INSERT OR REPLACE INTO cache_entries VALUES (?,?,'downloading',?)", (key, size, time.time()))
                        conn.commit()
                partial = settings.CACHE_FOLDER / (key + ".part")
                received = 0
                content_hash = DropboxHash()
                try:
                    with partial.open("wb") as output:
                        def write(chunk):
                            nonlocal received
                            with self.lock:
                                if received + len(chunk) > size:
                                    raise StorageError("Download exceeded its reserved size", 409)
                                if shutil.disk_usage(settings.CACHE_FOLDER).free - self.auxiliary_reserved - len(chunk) < settings.MIN_FREE_DISK_BYTES:
                                    raise StorageError("Download stopped to protect VM free disk space", 507)
                                output.write(chunk)
                                output.flush()
                                received += len(chunk)
                                self.reserved[key] = size - received
                            content_hash.update(chunk)
                        dropbox.download(reel, write)
                    if received != size or (reel.get("content_hash") and content_hash.hexdigest() != reel["content_hash"]):
                        raise StorageError("Download failed integrity verification; no partial file was served", 409)
                    with self.lock, get_db_connection() as conn:
                        partial.replace(self.path(key))
                        conn.execute("UPDATE cache_entries SET state='ready',accessed_at=? WHERE key=?", (time.time(), key))
                        conn.commit()
                        self.pins[key] = self.pins.get(key, 0) + 1
                        return self.path(key), key
                except BaseException:
                    partial.unlink(missing_ok=True)
                    with self.lock, get_db_connection() as conn:
                        conn.execute("DELETE FROM cache_entries WHERE key=?", (key,))
                        conn.commit()
                    raise
                finally:
                    with self.lock:
                        self.reserved.pop(key, None)

    def release(self, key):
        with self.lock, get_db_connection() as conn:
            self.pins[key] = max(0, self.pins.get(key, 0) - 1)
            conn.execute("UPDATE cache_entries SET accessed_at=? WHERE key=?", (time.time(), key))
            conn.commit()

    def status(self):
        settings.CACHE_FOLDER.mkdir(parents=True, exist_ok=True)
        with self.lock, get_db_connection() as conn:
            rows = [dict(r) for r in conn.execute("SELECT state,COUNT(*) AS files,COALESCE(SUM(size),0) AS bytes FROM cache_entries GROUP BY state")]
            return {"entries": rows, "budget_bytes": settings.CACHE_MAX_BYTES, "free_disk_bytes": shutil.disk_usage(settings.CACHE_FOLDER).free,
                    "min_free_disk_bytes": settings.MIN_FREE_DISK_BYTES, "ttl_seconds": settings.CACHE_TTL_SECONDS,
                    "max_downloads": settings.MAX_CONCURRENT_DOWNLOADS, "active_downloads": len(self.reserved),
                    "pinned_files": sum(v > 0 for v in self.pins.values())}


cache = MediaCache()


@contextmanager
def local_media(reel):
    if reel.get("storage_provider") == "dropbox":
        path, key = cache.acquire(reel)
        try:
            yield path
        finally:
            cache.release(key)
    else:
        from .icloud import ensure_icloud_downloaded
        if not ensure_icloud_downloaded(reel["filepath"], timeout=120):
            raise StorageError("Local media is unavailable on this machine", 404)
        yield Path(reel["filepath"])
