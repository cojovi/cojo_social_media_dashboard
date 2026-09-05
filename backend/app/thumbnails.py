import hashlib
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from .icloud import ensure_icloud_downloaded
from .settings import settings

logger = logging.getLogger("reelvault.thumbnails")


def is_ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def is_qlmanage_available() -> bool:
    return shutil.which("qlmanage") is not None


def _thumb_filename(video_path: str) -> str:
    info = Path(video_path).stat()
    identity = f"{video_path}:{info.st_size}:{info.st_mtime_ns}"
    path_hash = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
    return f"{Path(video_path).stem}_{path_hash}.jpg"


def generate_thumbnail_qlmanage(video_path: str, output_path: Path) -> bool:
    """
    macOS Quick Look thumbnail — often works with minimal iCloud fetch.
    """
    if not is_qlmanage_available():
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix=".ql_", dir=output_path.parent))

    try:
        cmd = [
            "qlmanage",
            "-t",
            "-s",
            "1024",
            "-o",
            str(temp_dir),
            str(video_path),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if res.returncode != 0:
            return False

        # qlmanage writes `<basename>.png` into the output directory
        candidates = list(temp_dir.glob(f"{Path(video_path).name}*.png"))
        if not candidates:
            candidates = list(temp_dir.glob("*.png"))
        if not candidates:
            return False

        source = candidates[0]
        if is_ffmpeg_available():
            conv = subprocess.run(
                ["ffmpeg", "-y", "-i", str(source), "-q:v", "2", str(output_path)],
                capture_output=True,
                text=True,
                timeout=15,
            )
            return conv.returncode == 0 and output_path.exists()

        png_target = output_path.with_suffix(".png")
        shutil.copy2(source, png_target)
        return png_target.exists()
    except Exception as exc:
        logger.error("qlmanage thumbnail failed for %s: %s", video_path, exc)
        return False
    finally:
        for leftover in temp_dir.glob("*"):
            leftover.unlink(missing_ok=True)
        temp_dir.rmdir()


def generate_thumbnail(video_path: str) -> Optional[str]:
    """
    Generates a JPEG thumbnail from the video file using ffmpeg.
    Returns absolute path to thumbnail, or None if failed.
    """
    if not is_ffmpeg_available() and not is_qlmanage_available():
        logger.warning("Neither ffmpeg nor qlmanage is available.")
        return None

    v_path = Path(video_path)
    if not v_path.exists():
        logger.error("Video file does not exist: %s", video_path)
        return None

    thumb_dir = Path(settings.THUMBNAILS_FOLDER)
    thumb_dir.mkdir(parents=True, exist_ok=True)
    thumb_path = thumb_dir / _thumb_filename(video_path)

    if thumb_path.exists():
        return str(thumb_path)

    if is_qlmanage_available():
        ql_png = thumb_path.with_suffix(".png")
        if generate_thumbnail_qlmanage(video_path, thumb_path):
            if thumb_path.exists():
                logger.info("Generated thumbnail via qlmanage: %s", thumb_path)
                return str(thumb_path)
            if ql_png.exists():
                logger.info("Generated thumbnail via qlmanage: %s", ql_png)
                return str(ql_png)

    if not is_ffmpeg_available():
        return None

    for seek in ("0.5", "0.0"):
        try:
            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                str(v_path),
                "-ss",
                seek,
                "-vframes",
                "1",
                "-f",
                "image2",
                str(thumb_path),
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
            if res.returncode == 0 and thumb_path.exists():
                logger.info("Generated thumbnail via ffmpeg: %s", thumb_path)
                return str(thumb_path)
        except subprocess.TimeoutExpired:
            logger.error("ffmpeg thumbnail timed out for %s", video_path)
            break
        except Exception as exc:
            logger.error("ffmpeg error for %s: %s", video_path, exc)
            break

    return None


def ensure_thumbnail_for_video(
    video_path: str,
    icloud_timeout: float = 45.0,
) -> Optional[str]:
    """
    Trigger iCloud download if needed, then generate a cached thumbnail.
    """
    if not ensure_icloud_downloaded(video_path, timeout=icloud_timeout):
        return None
    return generate_thumbnail(video_path)
