"""Small, revision-bound browsing clips; originals always use the existing media cache.

One serial encoder, durable jobs, exact-copy reuse, bounded scratch space and pinned
responses. Automatic backfill stops at capacity; only an explicit request evicts LRU
previews, so an archive larger than the budget cannot churn through downloads.
"""
import hashlib
import json
import logging
import math
import re
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from . import models
from .database import get_db_connection
from .dropbox_storage import StorageError
from .icloud import storage_status
from .media_cache import cache, cache_key, local_media
from .settings import settings

logger = logging.getLogger("reelvault.previews")
MAX_CLIP_BYTES = 1_000_000
SCRATCH_BYTES = 5_000_000  # Three capped segments + capped final MP4 + container overhead.
FORMAT_VERSION = "sampled-360-15fps-v1"


def preview_key(reel):
    content_hash = reel.get("content_hash") or ""
    if reel.get("storage_provider") == "dropbox" and re.fullmatch(r"[a-fA-F0-9]{64}", content_hash) and reel["file_size"] > 0:
        identity = f"hash:{content_hash.lower()}:{reel['file_size']}"
    else:
        identity = f"reel:{reel['id']}:{reel.get('source_version')}:{reel['file_size']}"
    return hashlib.sha256(f"{FORMAT_VERSION}:{identity}".encode()).hexdigest()


def run_ffmpeg(args, timeout=45):
    result = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout)
    if result.returncode:
        raise ValueError("This video could not be encoded as a preview. Full playback is still available.")
    return result


def encode_preview(source, directory):
    """Decode only three short seeks; never review audio or call an AI service."""
    result = run_ffmpeg(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                         "-of", "json", str(source)], timeout=15)
    duration = float(json.loads(result.stdout)["format"]["duration"])
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("The video has no readable duration.")
    samples = [(0, min(duration, 9))] if duration <= 9 else [
        (min(duration * fraction, duration - 3), 3) for fraction in (.15, .5, .85)]
    segments = []
    for index, (offset, length) in enumerate(samples):
        segment = directory / f"segment-{index}.mp4"
        run_ffmpeg(["ffmpeg", "-v", "error", "-nostdin", "-y", "-threads", "1", "-ss", str(offset),
                    "-i", str(source), "-t", str(length), "-map", "0:v:0", "-an", "-sn", "-dn",
                    "-map_metadata", "-1", "-vf",
                    "scale=360:360:force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1,fps=15",
                    "-filter_threads", "1", "-c:v", "libx264", "-threads", "1", "-preset", "veryfast",
                    "-crf", "28", "-maxrate", "500k", "-bufsize", "500k", "-pix_fmt", "yuv420p",
                    "-fs", str(MAX_CLIP_BYTES), str(segment)])
        if segment.stat().st_size > MAX_CLIP_BYTES:
            raise ValueError("Preview exceeded its size limit.")
        segments.append(segment)
    listing = directory / "segments.txt"
    listing.write_text("".join(f"file '{segment.name}'\n" for segment in segments))
    output = directory / "preview.mp4"
    run_ffmpeg(["ffmpeg", "-v", "error", "-nostdin", "-y", "-f", "concat", "-safe", "1", "-i", str(listing),
                "-map", "0:v:0", "-an", "-c", "copy", "-map_metadata", "-1", "-movflags", "+faststart",
                "-fs", str(MAX_CLIP_BYTES), str(output)])
    info = json.loads(run_ffmpeg(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(output)], 15).stdout)
    actual_duration = float(info["format"]["duration"])
    if (output.stat().st_size > MAX_CLIP_BYTES or output.stat().st_size <= 0
            or abs(actual_duration - min(duration, 9)) > .5
            or any(stream["codec_type"] != "video" for stream in info["streams"])):
        raise ValueError("Preview validation failed; the incomplete clip was discarded.")
    return output, actual_duration


class PreviewStore:
    def __init__(self):
        self.lock = threading.RLock()
        self.encoder_lock = threading.Lock()
        self.pins = {}
        self.reserved = 0
        self.blocked_reason = None
        self.stop_event = threading.Event()
        self.thread = None

    def path(self, key):
        return settings.PREVIEWS_FOLDER / f"{key}.mp4"

    def initialize(self):
        # This fixed child directory never points into the source archive or media cache.
        folder = settings.PREVIEWS_FOLDER
        if folder.is_symlink() or folder.resolve() in {settings.REELS_FOLDER.resolve(), settings.CACHE_FOLDER.resolve(), settings.THUMBNAILS_FOLDER.resolve()}:
            raise RuntimeError("Previews require a dedicated data/previews directory.")
        folder.mkdir(parents=True, exist_ok=True)
        with self.lock, get_db_connection() as conn:
            conn.execute("UPDATE preview_assets SET status='queued' WHERE status='running'")
            ready = {row['key'] for row in conn.execute("SELECT key FROM preview_assets WHERE status='ready'")}
            for path in folder.iterdir():
                if re.fullmatch(r"[a-f0-9]{64}\.mp4", path.name) and path.stem not in ready:
                    path.unlink()
                elif path.is_dir() and not path.is_symlink() and path.name.startswith("work-"):
                    shutil.rmtree(path)
            for key in ready:
                if not self.path(key).is_file():
                    conn.execute("UPDATE preview_assets SET status='evicted',size=0 WHERE key=?", (key,))
            # Honor a smaller configured budget after a restart as well.
            used = conn.execute("SELECT COALESCE(SUM(size),0) FROM preview_assets WHERE status='ready'").fetchone()[0]
            for row in conn.execute("SELECT key,size FROM preview_assets WHERE status='ready' ORDER BY accessed_at").fetchall():
                if used <= settings.PREVIEW_MAX_BYTES:
                    break
                self.path(row['key']).unlink(missing_ok=True)
                conn.execute("UPDATE preview_assets SET status='evicted',size=0 WHERE key=?", (row['key'],))
                used -= row['size']
            conn.commit()

    def eligible(self, reel):
        return reel['storage_status'] != 'missing' and reel['file_size'] > 0 and (
            reel['storage_provider'] != 'dropbox' or reel['file_size'] <= settings.CACHE_MAX_BYTES)

    def enqueue(self, reel, requested=False):
        if not self.eligible(reel):
            raise StorageError("Source is missing, empty, or larger than the original cache limit.", 409)
        key = preview_key(reel)
        with self.lock, get_db_connection() as conn:
            conn.execute("INSERT OR IGNORE INTO preview_assets(key,reel_id,status) VALUES (?,?,'queued')", (key, reel['id']))
            conn.execute("UPDATE preview_assets SET reel_id=? WHERE key=?", (reel['id'], key))
            if requested:
                if not self.path(key).is_file():
                    conn.execute("UPDATE preview_assets SET status='evicted',size=0 WHERE key=? AND status='ready'", (key,))
                conn.execute("""UPDATE preview_assets SET priority=1, available_at=0,
                    attempts=CASE WHEN status IN ('failed','evicted') THEN 0 ELSE attempts END,
                    status=CASE WHEN status IN ('failed','evicted') THEN 'queued' ELSE status END,
                    error=NULL WHERE key=?""", (key,))
            conn.commit()
        return self.info(reel)

    def reconcile(self):
        """Metadata only; runs periodically, discovering additions and retiring old revisions."""
        with get_db_connection() as conn:
            reels = [dict(row) for row in conn.execute("SELECT * FROM reels WHERE storage_status!='missing' AND file_size>0")]
        current = {preview_key(reel): reel for reel in reels if self.eligible(reel)}
        with self.lock, get_db_connection() as conn:
            for key, reel in current.items():
                # No automatic local/iCloud hydration. Explicit Preview can hydrate one file.
                auto = settings.AUTO_PREVIEWS and (reel['storage_provider'] == 'dropbox' or storage_status(reel['filepath']) == 'local')
                if auto:
                    conn.execute("INSERT OR IGNORE INTO preview_assets(key,reel_id,status) VALUES (?,?,'queued')", (key, reel['id']))
                conn.execute("UPDATE preview_assets SET reel_id=? WHERE key=?", (reel['id'], key))
            for row in conn.execute("SELECT key,status FROM preview_assets").fetchall():
                if row['key'] not in current and row['status'] != 'running' and not self.pins.get(row['key']):
                    self.path(row['key']).unlink(missing_ok=True)
                    conn.execute("DELETE FROM preview_assets WHERE key=?", (row['key'],))
            conn.commit()

    def info(self, reel):
        key = preview_key(reel)
        with self.lock, get_db_connection() as conn:
            row = conn.execute("SELECT * FROM preview_assets WHERE key=?", (key,)).fetchone()
        state = row['status'] if row else 'not_generated'
        if not self.eligible(reel):
            state = 'unavailable'
        elif state == 'ready' and not self.path(key).is_file():
            state = 'evicted'
        return {"status": state, "key": key, "bytes": row['size'] if row else 0,
                "duration_seconds": row['duration'] if row else 0,
                "url": f"/api/v1/reels/{reel['id']}/preview/video?key={key}" if state == 'ready' else None,
                "error": row['error'] if row else None, "sampled": True, "muted": True}

    def status(self):
        from .archive import get_state
        with self.lock, get_db_connection() as conn:
            counts = {row['status']: row['n'] for row in conn.execute("SELECT status,COUNT(*) n FROM preview_assets GROUP BY status")}
            used = conn.execute("SELECT COALESCE(SUM(size),0) FROM preview_assets WHERE status='ready'").fetchone()[0]
        return {"jobs": counts, "bytes": used, "reserved_bytes": self.reserved,
                "budget_bytes": settings.PREVIEW_MAX_BYTES, "auto_enabled": settings.AUTO_PREVIEWS,
                "paused": get_state('previews_paused', False), "blocked_reason": self.blocked_reason,
                "delay_seconds": settings.PREVIEW_DELAY_SECONDS}

    def reserve(self, requested):
        with self.lock, cache.lock, get_db_connection() as conn:
            used = conn.execute("SELECT COALESCE(SUM(size),0) FROM preview_assets WHERE status='ready'").fetchone()[0]
            if requested:
                for row in conn.execute("SELECT key,size FROM preview_assets WHERE status='ready' ORDER BY accessed_at").fetchall():
                    if used + SCRATCH_BYTES <= settings.PREVIEW_MAX_BYTES:
                        break
                    if self.pins.get(row['key']):
                        continue
                    self.path(row['key']).unlink(missing_ok=True)
                    conn.execute("UPDATE preview_assets SET status='evicted',size=0 WHERE key=?", (row['key'],))
                    used -= row['size']
            conn.commit()
            if used + SCRATCH_BYTES > settings.PREVIEW_MAX_BYTES:
                raise StorageError("Preview storage is full. Backfill is waiting; clicking Preview can replace an unused preview.", 507)
            if shutil.disk_usage(settings.PREVIEWS_FOLDER).free - sum(cache.reserved.values()) - SCRATCH_BYTES < settings.MIN_FREE_DISK_BYTES:
                raise StorageError("Preview generation is waiting for free server disk space.", 507)
            self.reserved = SCRATCH_BYTES
            cache.auxiliary_reserved = SCRATCH_BYTES

    def process_one(self):
        from .archive import get_state
        if not self.encoder_lock.acquire(blocking=False):
            return False
        job = None
        try:
            paused = get_state('previews_paused', False) or not settings.AUTO_PREVIEWS
            with self.lock, get_db_connection() as conn:
                rows = conn.execute("""SELECT * FROM preview_assets WHERE status='queued' AND available_at<=?
                    AND (?=0 OR priority=1) ORDER BY priority DESC, reel_id DESC""", (time.time(), int(paused))).fetchall()
                cached = {row['key'] for row in conn.execute("SELECT key FROM cache_entries WHERE state='ready'")}
                reels = {row['id']: dict(row) for row in conn.execute('SELECT * FROM reels')}
                candidates = []
                for row in rows:
                    reel = reels.get(row['reel_id'])
                    if not reel or not self.eligible(reel) or preview_key(reel) != row['key']:
                        continue
                    if not row['priority'] and reel['storage_provider'] != 'dropbox' and storage_status(reel['filepath']) != 'local':
                        continue
                    candidates.append((row, reel))
                if not candidates:
                    return False
                # Requests first, then originals already resident (including new summary jobs).
                job, reel = max(candidates, key=lambda pair: (pair[0]['priority'], cache_key(pair[1]) in cached, pair[1]['id']))
                conn.execute("UPDATE preview_assets SET status='running' WHERE key=?", (job['key'],))
                conn.commit()
            self.reserve(bool(job['priority']))
            with local_media(reel) as source, tempfile.TemporaryDirectory(prefix='work-', dir=settings.PREVIEWS_FOLDER) as folder:
                before = source.stat()
                if reel['storage_provider'] != 'dropbox':
                    if time.time() - before.st_mtime < settings.FILE_SETTLE_SECONDS:
                        raise StorageError("Waiting for the local file to finish copying.", 503)
                    if reel.get('source_version') and reel['source_version'] != f'{before.st_size}:{before.st_mtime_ns}':
                        raise StorageError("Source changed; rescan before generating a preview.", 409)
                output, duration = encode_preview(source, Path(folder))
                after = source.stat()
                current = models.get_reel_by_id(reel['id'])
                if (not current or not self.eligible(current) or preview_key(current) != job['key']
                        or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns)):
                    raise StorageError("Source changed during preview generation; the clip was discarded.", 409)
                with self.lock, get_db_connection() as conn:
                    # Fence the publish against a simultaneous catalog scan.
                    conn.execute('BEGIN IMMEDIATE')
                    latest = conn.execute('SELECT * FROM reels WHERE id=?', (reel['id'],)).fetchone()
                    if not latest or not self.eligible(dict(latest)) or preview_key(dict(latest)) != job['key']:
                        raise StorageError("Source revision changed; preview discarded.", 409)
                    output.replace(self.path(job['key']))
                    conn.execute("UPDATE preview_assets SET status='ready',size=?,duration=?,accessed_at=?,error=NULL WHERE key=?",
                                 (self.path(job['key']).stat().st_size, duration, time.time(), job['key']))
                    conn.commit()
            self.blocked_reason = None
            return True
        except Exception as exc:
            if job is None:
                raise
            capacity = isinstance(exc, StorageError) and exc.status == 507
            retry = capacity or (isinstance(exc, StorageError) and exc.status in (429, 503) and job['attempts'] < 2)
            error = str(exc) if isinstance(exc, (StorageError, ValueError)) else "Preview processing failed; retry this reel or use full playback."
            with self.lock, get_db_connection() as conn:
                conn.execute("UPDATE preview_assets SET status=?,attempts=attempts+?,available_at=?,error=? WHERE key=?",
                             ('queued' if retry else 'failed', 0 if capacity else 1, time.time() + 300, error[:400], job['key']))
                conn.commit()
            if capacity:
                self.blocked_reason = error
            logger.warning("Preview %s: %s", job['key'][:12], type(exc).__name__)
            return True
        finally:
            with self.lock, cache.lock:
                self.reserved = 0
                cache.auxiliary_reserved = 0
            self.encoder_lock.release()

    def acquire(self, reel, expected_key):
        key = preview_key(reel)
        if key != expected_key:
            raise StorageError("Preview belongs to an older revision; refresh the reel.", 409)
        with self.lock, get_db_connection() as conn:
            if self.info(reel)['status'] != 'ready':
                raise StorageError("Preview is not ready. Request it first.", 404)
            self.pins[key] = self.pins.get(key, 0) + 1
            conn.execute("UPDATE preview_assets SET accessed_at=? WHERE key=?", (time.time(), key))
            conn.commit()
            return self.path(key), key

    def release(self, key):
        with self.lock:
            self.pins[key] = max(0, self.pins.get(key, 0) - 1)

    def start(self):
        self.stop_event.clear()
        self.initialize()
        self.thread = threading.Thread(target=self.loop, daemon=True, name='reel-previews')
        self.thread.start()

    def loop(self):
        next_scan = 0
        while not self.stop_event.is_set():
            try:
                if time.monotonic() >= next_scan:
                    self.reconcile()
                    next_scan = time.monotonic() + 60
                worked = self.process_one()
            except Exception:
                logger.exception("Preview worker iteration failed")
                worked = False
            self.stop_event.wait(settings.PREVIEW_DELAY_SECONDS if worked else 2)

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=1)


previews = PreviewStore()
