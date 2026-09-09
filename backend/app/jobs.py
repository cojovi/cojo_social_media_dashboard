"""Small durable SQLite job queue. One service process; transfers and AI run separately."""
import json
import logging
import threading
import time
import uuid
from .database import get_db_connection
from .settings import settings
from . import models
from .media_cache import cache, local_media

logger = logging.getLogger("reelvault.jobs")


def serialize(row):
    result = dict(row)
    result["result"] = json.loads(result["result"]) if result["result"] else None
    return result


def enqueue(kind, reel_id=None):
    with get_db_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        reel = conn.execute("SELECT * FROM reels WHERE id=?", (reel_id,)).fetchone() if reel_id else None
        if reel_id and not reel:
            raise ValueError("Reel not found")
        version = reel["source_version"] if reel else None
        existing = conn.execute("""SELECT * FROM transfer_jobs WHERE kind=? AND reel_id IS ? AND source_version IS ?
            AND status IN ('queued','running') ORDER BY created_at LIMIT 1""", (kind, reel_id, version)).fetchone()
        if existing:
            return serialize(existing)
        key = uuid.uuid4().hex
        now = time.time()
        conn.execute("INSERT INTO transfer_jobs VALUES (?,?,?,?, 'queued', NULL,NULL,?,?)", (key, kind, reel_id, version, now, now))
        conn.commit()
        return serialize(conn.execute("SELECT * FROM transfer_jobs WHERE id=?", (key,)).fetchone())


def process_one(kinds):
    with get_db_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        placeholders = ','.join('?' for _ in kinds)
        job = conn.execute(f"SELECT * FROM transfer_jobs WHERE status='queued' AND kind IN ({placeholders}) ORDER BY created_at LIMIT 1", kinds).fetchone()
        if not job:
            return False
        conn.execute("UPDATE transfer_jobs SET status='running',updated_at=? WHERE id=?", (time.time(), job["id"]))
        conn.commit()
    try:
        reel = models.get_reel_by_id(job["reel_id"]) if job["reel_id"] else None
        if job["reel_id"] and (not reel or reel["source_version"] != job["source_version"]):
            raise ValueError("Source revision changed; submit a new job")
        if job["kind"] == "materialize":
            with local_media(reel):
                result = {"reel_id": reel["id"], "download_url": f"/api/v1/reels/{reel['id']}/download",
                          "source_version": reel["source_version"]}
        elif job["kind"] == "scan":
            from .archive import run_scan
            result = run_scan()
            if result is None:
                raise ValueError('Another scan is already running. Check storage status for its result.')
        elif job["kind"] == "analyze":
            from .routes.reels import run_ai_analysis
            result = run_ai_analysis(reel["id"])
        elif job["kind"] == "thumbnail":
            from .routes.reels import generate_single_thumbnail
            result = generate_single_thumbnail(reel["id"])
        else:
            raise ValueError("Unsupported job kind")
        with get_db_connection() as conn:
            conn.execute("UPDATE transfer_jobs SET status='succeeded',result=?,updated_at=? WHERE id=?",
                         (json.dumps(result), time.time(), job["id"]))
            conn.commit()
    except Exception as exc:
        # Don't persist SDK errors containing request credentials, signed URLs or large bodies.
        from .dropbox_storage import StorageError
        from fastapi import HTTPException
        error = str(exc) if isinstance(exc, (StorageError, ValueError)) else str(exc.detail) if isinstance(exc, HTTPException) else f"{type(exc).__name__}: job failed; inspect server logs"
        for secret in (settings.GEMINI_API_KEY, settings.ADMIN_TOKEN, settings.AGENT_TOKEN):
            if secret:
                error = error.replace(secret, "[redacted]")
        with get_db_connection() as conn:
            conn.execute("UPDATE transfer_jobs SET status='failed',error=?,updated_at=? WHERE id=?", (error[:1000], time.time(), job["id"]))
            conn.commit()
        logger.warning("Job %s failed (%s)", job["id"], type(exc).__name__)
    return True


class JobWorker:
    def __init__(self):
        self.stop_event = threading.Event()
        self.threads = []

    def start(self):
        cache.start()  # Enforce single hosting process, including across restarts.
        with get_db_connection() as conn:
            conn.execute("UPDATE transfer_jobs SET status='queued' WHERE status='running' AND kind IN ('materialize','scan','thumbnail')")
            conn.execute("UPDATE transfer_jobs SET status='failed',error='Server restarted during AI work; check usage before retrying' WHERE status='running'")
            conn.commit()
        for kinds in (["materialize"],) * settings.MAX_CONCURRENT_DOWNLOADS + (["analyze", "thumbnail"], ["scan"]):
            thread = threading.Thread(target=self.loop, args=(kinds,), daemon=True)
            thread.start()
            self.threads.append(thread)
        thread = threading.Thread(target=self.maintenance, daemon=True)
        thread.start()
        self.threads.append(thread)

    def loop(self, kinds):
        while not self.stop_event.is_set():
            try:
                if process_one(kinds):
                    continue
            except Exception:
                logger.exception("Job worker iteration failed")
            self.stop_event.wait(1)

    def maintenance(self):
        while not self.stop_event.wait(60):
            try:
                cache.cleanup()
            except Exception as exc:
                logger.warning("Cache maintenance: %s", type(exc).__name__)

    def stop(self):
        self.stop_event.set()
        for thread in self.threads:
            thread.join(timeout=1)
