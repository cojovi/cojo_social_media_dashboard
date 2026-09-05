"""Metadata-only availability detection; downloading is always an explicit operation."""
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

logger = logging.getLogger("reelvault.icloud")
try:
    import Foundation
    HAS_FOUNDATION = True
except ImportError:
    HAS_FOUNDATION = False

# macOS SF_DATALESS applies to both iCloud and modern File Provider placeholders.
SF_DATALESS = 0x40000000


def storage_status(filepath: str) -> str:
    try:
        info = os.stat(filepath)
    except FileNotFoundError:
        stub = Path(filepath).with_name(f".{Path(filepath).name}.icloud")
        return "cloud" if stub.exists() else "missing"
    except OSError:
        return "unknown"
    if getattr(info, "st_flags", 0) & SF_DATALESS:
        return "cloud"
    if HAS_FOUNDATION:
        try:
            url = Foundation.NSURL.fileURLWithPath_(filepath)
            ok, downloaded, _ = url.getResourceValue_forKey_error_(
                None, Foundation.NSURLUbiquitousItemIsDownloadedKey, None)
            if ok and downloaded is not None and not downloaded:
                return "cloud"
        except Exception:
            pass
    return "local"


def is_icloud_file_downloaded(filepath: str) -> bool:
    return storage_status(filepath) == "local"


def ensure_icloud_downloaded(filepath: str, timeout: float = 45.0) -> bool:
    deadline = time.monotonic() + timeout
    state = storage_status(filepath)
    if state == "local":
        return True
    if state == "missing":
        return False
    if HAS_FOUNDATION and "com~apple~CloudDocs" in filepath:
        try:
            url = Foundation.NSURL.fileURLWithPath_(filepath)
            ok, error = Foundation.NSFileManager.defaultManager().startDownloadingUbiquitousItemAtURL_error_(url, None)
            if not ok:
                logger.warning("iCloud download request failed: %s", error)
                return False
        except Exception:
            logger.exception("iCloud download request failed")
            return False
    else:
        # A separate, bounded reader lets File Provider hydrate on demand without
        # hanging an API worker indefinitely. Never used by scans or quick summaries.
        try:
            subprocess.run([sys.executable, "-c",
                            "import sys; f=open(sys.argv[1],'rb'); f.read(1); f.close()",
                            filepath], check=True, capture_output=True, timeout=timeout)
        except (OSError, subprocess.SubprocessError):
            return False
    while time.monotonic() < deadline:
        if storage_status(filepath) == "local":
            return True
        time.sleep(0.5)
    return False
