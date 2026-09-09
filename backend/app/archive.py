"""Persistent quick-description queue and startup/periodic folder discovery."""
import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from .database import get_db_connection
from .settings import settings
from . import models
from .scanner import scan_reels_folder
from .quick_summary import prepare_stills, summarize_stills, WaitingForLocalMedia
from .usage import quick_request_reserve, usage_summary

logger = logging.getLogger('reelvault.archive')
_scan_lock = threading.Lock()


def now():
    return datetime.now(timezone.utc).isoformat()


def set_state(key, value):
    with get_db_connection() as conn:
        conn.execute('INSERT OR REPLACE INTO archive_state (key,value) VALUES (?,?)', (key, json.dumps(value)))
        conn.commit()


def get_state(key, default=None):
    with get_db_connection() as conn:
        row = conn.execute('SELECT value FROM archive_state WHERE key=?', (key,)).fetchone()
        return json.loads(row['value']) if row else default


def enqueue_missing(reel_ids=None, retry=False):
    stamp = now()
    with get_db_connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        ids = reel_ids if reel_ids is not None else [r['id'] for r in conn.execute(
            "SELECT id FROM reels WHERE COALESCE(quick_summary,'')='' AND COALESCE(ai_summary,'')=''")]
        added = 0
        for reel_id in set(ids):
            reel = conn.execute("SELECT id FROM reels WHERE id=? AND COALESCE(quick_summary,'')=''", (reel_id,)).fetchone()
            if not reel:
                continue
            result = conn.execute("INSERT OR IGNORE INTO summary_jobs (reel_id,updated_at) VALUES (?,?)", (reel_id, stamp))
            added += result.rowcount
            if retry:
                result = conn.execute("UPDATE summary_jobs SET status='queued', attempts=0, available_at=0, error=NULL, updated_at=? WHERE reel_id=? AND status IN ('failed','waiting_local')", (stamp, reel_id))
                added += result.rowcount
        conn.commit()
    return added


def run_scan():
    if not _scan_lock.acquire(blocking=False):
        return None
    set_state('scan', {'running': True, 'started_at': now(), 'error': None})
    try:
        if settings.STORAGE_PROVIDER == 'dropbox':
            from .dropbox_storage import sync_dropbox
            result = sync_dropbox()
        else:
            result = scan_reels_folder()
        if settings.AUTO_QUICK_SUMMARY:
            enqueue_missing()
        set_state('scan', {'running': False, 'finished_at': now(), 'error': None, **result})
        return result
    except Exception as exc:
        set_state('scan', {'running': False, 'finished_at': now(), 'error': str(exc)})
        raise
    finally:
        _scan_lock.release()


def status():
    with get_db_connection() as conn:
        counts = {r['status']: r['count'] for r in conn.execute('SELECT status,COUNT(*) AS count FROM summary_jobs GROUP BY status')}
        storage = {r['storage_status']: r['count'] for r in conn.execute('SELECT storage_status,COUNT(*) AS count FROM reels GROUP BY storage_status')}
        recent = [dict(r) for r in conn.execute('''SELECT j.*,r.filename FROM summary_jobs j JOIN reels r ON r.id=j.reel_id
            ORDER BY CASE j.status WHEN 'processing' THEN 0 WHEN 'failed' THEN 1 WHEN 'waiting_local' THEN 2 ELSE 3 END,
            j.updated_at DESC LIMIT 12''')]
        described = conn.execute("SELECT COUNT(*) FROM reels WHERE COALESCE(quick_summary,'')!='' OR COALESCE(ai_summary,'')!=''").fetchone()[0]
    usage = usage_summary()
    reserve = quick_request_reserve()
    blocked = (not settings.is_gemini_enabled or reserve is None or
               usage['quick_today_usd'] + reserve > settings.QUICK_SUMMARY_DAILY_BUDGET_USD)
    return dict(storage_provider=settings.STORAGE_PROVIDER, scan=get_state('scan', {}), scan_interval_seconds=settings.SCAN_INTERVAL_SECONDS,
        auto_scan=settings.AUTO_SCAN, auto_quick_summary=settings.AUTO_QUICK_SUMMARY,
        quick_model=settings.QUICK_SUMMARY_MODEL, paused=get_state('paused', False),
        blocked_reason='Configure Gemini and a priced quick model, or increase the daily estimate limit.' if blocked else None,
        jobs=counts, storage=storage, described=described, recent_jobs=recent, usage=usage)


def process_one():
    if get_state('paused', False) or not settings.is_gemini_enabled:
        return False
    reserve = quick_request_reserve()
    if reserve is None or usage_summary()['quick_today_usd'] + reserve > settings.QUICK_SUMMARY_DAILY_BUDGET_USD:
        return False
    with get_db_connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        # A processing lease protects against overlapping workers and survives crashes.
        conn.execute("UPDATE summary_jobs SET status='queued' WHERE status='processing' AND available_at<?", (time.time(),))
        job = conn.execute("""SELECT * FROM summary_jobs WHERE status IN ('queued','waiting_local') AND available_at<=?
            ORDER BY status='waiting_local', reel_id DESC LIMIT 1""", (time.time(),)).fetchone()
        if not job:
            return False
        reel_id = job['reel_id']
        conn.execute("UPDATE summary_jobs SET status='processing',available_at=?,updated_at=? WHERE reel_id=?", (time.time()+600, now(), reel_id))
        conn.commit()
    reel = models.get_reel_by_id(reel_id)
    try:
        if not reel:
            return False
        if reel.get('quick_summary'):
            with get_db_connection() as conn:
                conn.execute("UPDATE summary_jobs SET status='done',updated_at=? WHERE reel_id=?", (now(), reel_id))
                conn.commit()
            return True
        frames, source, duration = prepare_stills(reel)
        result = summarize_stills(reel_id, frames, source)
        with get_db_connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            current = conn.execute('SELECT source_version FROM reels WHERE id=?', (reel_id,)).fetchone()
            if not current or current['source_version'] != reel['source_version']:
                raise WaitingForLocalMedia('Source changed during analysis; description will be retried.')
            thumb_name = reel.get('thumbnail_path')
            if not thumb_name or not (settings.THUMBNAILS_FOLDER / Path(thumb_name).name).is_file():
                import hashlib
                token = hashlib.sha256(str(reel['source_version']).encode()).hexdigest()[:10]
                thumb_name = f"quick-{reel_id}-{token}.jpg"
                settings.THUMBNAILS_FOLDER.mkdir(parents=True, exist_ok=True)
                (settings.THUMBNAILS_FOLDER / thumb_name).write_bytes(frames[0])
            conn.execute('''UPDATE reels SET quick_summary=?,quick_category=?,quick_tags=?,quick_summary_source=?,
                quick_summary_model=?,quick_summary_at=?,duration_seconds=?,thumbnail_path=?,updated_at=? WHERE id=?''',
                (result['summary'],result['category'],' '.join(result['tags']),source,settings.QUICK_SUMMARY_MODEL,
                 now(),duration,thumb_name,now(),reel_id))
            conn.execute("UPDATE summary_jobs SET status='done',error=NULL,updated_at=? WHERE reel_id=?", (now(),reel_id))
            conn.commit()
        return True
    except WaitingForLocalMedia as exc:
        with get_db_connection() as conn:
            conn.execute("UPDATE summary_jobs SET status='waiting_local',available_at=?,error=?,updated_at=? WHERE reel_id=?",
                         (time.time()+settings.SCAN_INTERVAL_SECONDS,str(exc),now(),reel_id))
            conn.commit()
    except Exception as exc:
        attempts = job['attempts'] + 1
        # Bounded exponential retries; auth/quota failures back off the entire worker.
        code = getattr(exc, 'code', None)
        if code in (400, 401, 403, 404, 429):
            set_state('paused', True)
        message = str(exc).replace(settings.GEMINI_API_KEY, '[redacted]') if settings.GEMINI_API_KEY else str(exc)
        with get_db_connection() as conn:
            conn.execute("UPDATE summary_jobs SET status=?,attempts=?,available_at=?,error=?,updated_at=? WHERE reel_id=?",
                ('failed' if attempts >= 3 or code in (400,401,403,404,429) else 'queued',attempts,
                 time.time()+min(3600,60*2**attempts),message[:600],now(),reel_id))
            conn.commit()
        logger.warning('Quick description %s failed (%s)', reel_id, type(exc).__name__)
    return True


class ArchiveWorker:
    """One local backend instance owns the loops. No browser must stay open."""
    def __init__(self):
        self.stop_event = threading.Event()
        self.threads = []
        self.lock_file = None

    def start(self):
        import fcntl
        self.lock_file = open(settings.DATABASE_PATH.with_suffix('.worker.lock'), 'a')
        try:
            fcntl.flock(self.lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock_file.close()
            self.lock_file = None
            return
        if settings.AUTO_SCAN:
            self.threads.append(threading.Thread(target=self.scan_loop, daemon=True))
        self.threads.append(threading.Thread(target=self.summary_loop, daemon=True))
        for thread in self.threads:
            thread.start()

    def scan_loop(self):
        while not self.stop_event.is_set():
            try:
                from .dropbox_storage import dropbox
                if settings.STORAGE_PROVIDER != 'dropbox' or dropbox.status()['connected']:
                    run_scan()
                else:
                    set_state('scan', {'running': False, 'error': None, 'waiting_for': 'dropbox_connection'})
            except Exception:
                logger.exception('Automatic scan failed')
            self.stop_event.wait(settings.SCAN_INTERVAL_SECONDS)

    def summary_loop(self):
        while not self.stop_event.is_set():
            try:
                worked = process_one()
            except Exception:
                logger.exception('Summary worker error')
                worked = False
            self.stop_event.wait(settings.QUICK_SUMMARY_DELAY_SECONDS if worked else 5)

    def stop(self):
        self.stop_event.set()
        for thread in self.threads:
            thread.join(timeout=1)
        # Keep the OS lock until an in-flight thread exits or the process ends.
        if self.lock_file and not any(t.is_alive() for t in self.threads):
            self.lock_file.close()
