import logging
import time

logger = logging.getLogger("reelvault.icloud")

try:
    import Foundation
    HAS_FOUNDATION = True
except ImportError:
    HAS_FOUNDATION = False


def is_icloud_file_downloaded(filepath: str) -> bool:
    """
    True when the file is fully cached locally on macOS iCloud Drive.
    On non-macOS or without pyobjc, assumes available.
    """
    if not HAS_FOUNDATION:
        return True
    try:
        url = Foundation.NSURL.fileURLWithPath_(filepath)
        success, is_downloaded, _error = url.getResourceValue_forKey_error_(
            None,
            Foundation.NSURLUbiquitousItemIsDownloadedKey,
            None,
        )
        if success:
            if is_downloaded is None:
                return True
            return bool(is_downloaded)
        return True
    except Exception:
        return True


def ensure_icloud_downloaded(filepath: str, timeout: float = 45.0) -> bool:
    """
    Request an iCloud-evicted file and wait until it is locally available.
    Returns True if the file can be read (already local or download finished).
    """
    if is_icloud_file_downloaded(filepath):
        return True

    if not HAS_FOUNDATION:
        return True

    try:
        url = Foundation.NSURL.fileURLWithPath_(filepath)
        fm = Foundation.NSFileManager.defaultManager()
        started = fm.startDownloadingUbiquitousItemAtURL_error_(url, None)
        if not started:
            logger.warning("Could not start iCloud download for %s", filepath)

        deadline = time.time() + timeout
        while time.time() < deadline:
            if is_icloud_file_downloaded(filepath):
                logger.info("iCloud file ready: %s", filepath)
                return True
            time.sleep(0.5)

        ready = is_icloud_file_downloaded(filepath)
        if not ready:
            logger.warning("Timed out waiting for iCloud download: %s", filepath)
        return ready
    except Exception as exc:
        logger.error("iCloud download error for %s: %s", filepath, exc)
        return False
