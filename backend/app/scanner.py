"""Fast recursive discovery. A scan never reads video bytes or hydrates cloud files."""
import logging
import os
import shutil
import subprocess
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from .settings import settings
from .database import get_db_connection
from . import models
from .icloud import storage_status
from .thumbnails import generate_thumbnail

logger = logging.getLogger("reelvault.scanner")
VALID_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".webm", ".mkv"}


def is_ffprobe_available():
    return shutil.which("ffprobe") is not None


def get_video_duration(filepath: str) -> float:
    if not is_ffprobe_available():
        return 0.0
    try:
        result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                 "-of", "default=noprint_wrappers=1:nokey=1", filepath],
                                capture_output=True, text=True, timeout=10)
        return max(0.0, float(result.stdout.strip())) if result.returncode == 0 else 0.0
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0.0


def scan_reels_folder():
    folder = Path(settings.REELS_FOLDER).resolve()
    if not folder.is_dir():
        raise FileNotFoundError(f"Reels folder is unavailable: {folder}. Check that cloud storage is running.")
    now = datetime.now(timezone.utc).isoformat()
    stats = dict(scanned=0, added=0, updated=0, missing=0, skipped=0)
    entries = []
    seen = set()
    errors = []
    for root, dirs, files in os.walk(folder, onerror=errors.append, followlinks=False):
        dirs[:] = [d for d in dirs if not (Path(root) / d).is_symlink()]
        for name in files:
            path = Path(root) / name
            stub = name.startswith('.') and name.endswith('.icloud')
            logical = path.with_name(name[1:-7]) if stub else path
            if logical.suffix.lower() not in VALID_EXTENSIONS or path.is_symlink():
                continue
            filepath = unicodedata.normalize('NFC', str(logical.absolute()))
            seen.add(filepath)
            try:
                stat = path.stat()
                state = "cloud" if stub else storage_status(str(path))
                # Ignore files still arriving; record in seen so an existing row isn't marked missing.
                if not stub and (not stat.st_size or time.time() - stat.st_mtime < settings.FILE_SETTLE_SECONDS):
                    stats['skipped'] += 1
                    continue
                entries.append((filepath, logical, stat, state, stub))
            except OSError as exc:
                errors.append(exc)
    # One transaction prevents readers seeing a partly reconciled catalog.
    with get_db_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = {r['filepath']: dict(r) for r in conn.execute("SELECT * FROM reels")}
        for filepath, path, stat, state, stub in entries:
            old = existing.get(filepath)
            version = (old or {}).get('source_version') if stub else f"{stat.st_size}:{stat.st_mtime_ns}"
            changed = bool(old and old['source_version'] and version and old['source_version'] != version)
            size = (old or {}).get('file_size', 0) if stub else stat.st_size
            modified = (old or {}).get('created_at', now) if stub else datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()
            if old:
                conn.execute("""UPDATE reels SET file_size=?, created_at=?, storage_status=?,
                    source_version=?, last_seen_at=? WHERE id=?""",
                    (size, modified, state, version, now, old['id']))
                if old.get('thumbnail_path') and not (settings.THUMBNAILS_FOLDER / Path(old['thumbnail_path']).name).is_file():
                    conn.execute('UPDATE reels SET thumbnail_path=NULL WHERE id=?', (old['id'],))
                if changed:
                    conn.execute("""UPDATE reels SET duration_seconds=0, thumbnail_path=NULL,
                        quick_summary=NULL, quick_tags=NULL, quick_category=NULL, quick_summary_source=NULL,
                        quick_summary_at=NULL, quick_summary_model=NULL WHERE id=?""", (old['id'],))
                    conn.execute("DELETE FROM summary_jobs WHERE reel_id=? AND status != 'processing'", (old['id'],))
                stats['updated'] += 1
            else:
                conn.execute("""INSERT INTO reels (filename,filepath,file_extension,file_size,duration_seconds,
                    created_at,updated_at,discovered_at,storage_status,source_version,last_seen_at)
                    VALUES (?,?,?,?,0,?,?,?,?,?,?)""",
                    (path.name, filepath, path.suffix.lower(), size, modified, now, now, state, version, now))
                stats['added'] += 1
            stats['scanned'] += 1
        # A disconnected/incomplete tree must never mark an entire archive missing.
        if not errors:
            for filepath, old in existing.items():
                if filepath.startswith(str(folder) + os.sep) and filepath not in seen:
                    conn.execute("UPDATE reels SET storage_status='missing' WHERE id=?", (old['id'],))
                    stats['missing'] += 1
        conn.commit()
    if errors:
        raise OSError(f"Scan incomplete ({len(errors)} filesystem errors). Missing-file reconciliation was skipped.")
    return stats


def backfill_thumbnails(limit=20, icloud_timeout=0):
    # Local files only, regardless of caller. Offloaded media waits for explicit playback.
    candidates = models.get_reels_missing_thumbnails(10000)
    local = [r for r in candidates if storage_status(r['filepath']) == 'local'][:limit]
    generated = 0
    for reel in local:
        thumb = generate_thumbnail(reel['filepath'])
        if thumb:
            models.update_reel(reel['id'], {'thumbnail_path': Path(thumb).name})
            generated += 1
    return dict(processed=len(local), generated=generated, failed=len(local)-generated,
                remaining=models.count_reels_missing_thumbnails())
