import os
import subprocess
import shutil
import unicodedata
from pathlib import Path
from datetime import datetime
import logging
from typing import Dict, Any, List

from .settings import settings
from . import models
from .icloud import is_icloud_file_downloaded
from .thumbnails import ensure_thumbnail_for_video, generate_thumbnail

logger = logging.getLogger("reelvault.scanner")

VALID_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".webm", ".mkv"}

def is_ffprobe_available() -> bool:
    return shutil.which("ffprobe") is not None

def get_video_duration(filepath: str) -> float:
    """
    Query ffprobe to get duration in seconds.
    Returns 0.0 on failure.
    """
    if not is_ffprobe_available():
        return 0.0
        
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            filepath
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            val = res.stdout.strip()
            return float(val) if val else 0.0
        return 0.0
    except Exception as e:
        logger.error(f"Error reading duration via ffprobe for {filepath}: {e}")
        return 0.0

def scan_reels_folder() -> Dict[str, int]:
    """
    Scans the configured REELS_FOLDER for videos.
    Inserts newly discovered videos, and updates file attributes for existing ones.
    Generates thumbnails for locally present files.
    """
    folder_path = Path(settings.REELS_FOLDER)
    if not folder_path.exists():
        logger.error(f"Reels folder does not exist: {folder_path}")
        return {"scanned": 0, "added": 0, "updated": 0}
        
    scanned_count = 0
    added_count = 0
    updated_count = 0
    
    # Iterate files in directory recursively
    for root, _, files in os.walk(folder_path):
        for file in files:
            file_path = Path(root) / file
            ext = file_path.suffix.lower()
            
            if ext in VALID_EXTENSIONS:
                scanned_count += 1
                try:
                    # Gather system stats
                    stat = file_path.stat()
                    file_size = stat.st_size
                    created_time = datetime.fromtimestamp(stat.st_mtime).isoformat()
                    
                    # Normalize path
                    normalized_filepath = unicodedata.normalize('NFC', str(file_path.resolve()))
                    
                    # Check if already present in DB
                    existing = models.get_reel_by_filepath(normalized_filepath)
                    
                    # Determine local presence / download status
                    is_dl = is_icloud_file_downloaded(str(file_path))
                    
                    # Fetch duration (reuse cached if possible to avoid expensive subprocess spawning)
                    duration = 0.0
                    if existing and existing.get("duration_seconds") and existing["duration_seconds"] > 0:
                        duration = existing["duration_seconds"]
                    elif is_dl:
                        duration = get_video_duration(str(file_path))
                    
                    # Prep data dictionary
                    reel_data = {
                        "filename": file_path.name,
                        "filepath": normalized_filepath,
                        "file_extension": ext,
                        "file_size": file_size,
                        "duration_seconds": duration,
                        "created_at": created_time
                    }
                    
                    # Upsert
                    reel_id = models.upsert_scanned_reel(reel_data)
                    
                    if existing:
                        updated_count += 1
                    else:
                        added_count += 1
                        existing = models.get_reel_by_id(reel_id)
                        
                    # Thumbnail — retry missing thumbs; pull from iCloud on demand
                    if existing and not existing.get("thumbnail_path"):
                        thumb_path = ensure_thumbnail_for_video(
                            reel_data["filepath"],
                            icloud_timeout=20.0 if not is_dl else 45.0,
                        )
                        if thumb_path:
                            models.update_reel(reel_id, {"thumbnail_path": Path(thumb_path).name})
                            
                except Exception as e:
                    logger.error(f"Failed scanning file {file_path}: {e}")
                    
    return {
        "scanned": scanned_count,
        "added": added_count,
        "updated": updated_count
    }


def backfill_thumbnails(limit: int = 20, icloud_timeout: float = 45.0) -> Dict[str, int]:
    """
    Generate thumbnails for reels missing them.
    Triggers selective iCloud downloads — does not bulk-download the whole library.
    """
    missing = models.get_reels_missing_thumbnails(limit)
    generated = 0
    failed = 0

    for reel in missing:
        try:
            thumb_path = ensure_thumbnail_for_video(
                reel["filepath"],
                icloud_timeout=icloud_timeout,
            )
            if thumb_path:
                models.update_reel(reel["id"], {"thumbnail_path": Path(thumb_path).name})
                generated += 1
            else:
                failed += 1
        except Exception as exc:
            logger.error("Thumbnail backfill failed for %s: %s", reel.get("filepath"), exc)
            failed += 1

    return {
        "processed": len(missing),
        "generated": generated,
        "failed": failed,
        "remaining": models.count_reels_missing_thumbnails(),
    }

