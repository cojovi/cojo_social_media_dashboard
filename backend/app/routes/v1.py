"""Versioned agent API. Mutations that approve/edit captions remain owner-only."""
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from .. import models, jobs
from ..database import get_db_connection
from ..dropbox_storage import dropbox
from ..media_cache import cache
from ..settings import settings
from ..schemas import ReadyQueueResponse
from ..previews import previews

router = APIRouter(prefix="/v1", tags=["agent API v1"])


@router.get('/guide', response_class=PlainTextResponse)
def agent_guide():
    """The agent guide shipped with this exact application release."""
    path = settings.PROJECT_ROOT / 'AGENT_API.md'
    if not path.is_file():
        path = Path(__file__).resolve().parents[2] / 'AGENT_API.md'
    if not path.is_file():
        raise HTTPException(503, 'Agent guide is missing from this deployment')
    return PlainTextResponse(path.read_text(), media_type='text/markdown')


@router.get("/storage")
def storage_status():
    from ..archive import get_state
    return {"provider": settings.STORAGE_PROVIDER, "dropbox": dropbox.status(), "cache": cache.status(), "previews": previews.status(),
            "scan": get_state("scan", {}), "sync_interval_seconds": settings.SCAN_INTERVAL_SECONDS}


class DropboxBegin(BaseModel):
    app_key: str = Field(pattern=r"^[a-zA-Z0-9]{8,100}$")
    folder: str = Field(default="", max_length=1000)


@router.post("/storage/dropbox/begin")
def begin(body: DropboxBegin):
    folder = body.folder.strip().rstrip("/")
    if folder and not folder.startswith("/"):
        raise HTTPException(422, "Use an absolute Dropbox path, or blank for the app folder root")
    if settings.STORAGE_PROVIDER != "dropbox":
        raise HTTPException(409, "Server must be configured for Dropbox before connecting")
    return dropbox.begin(body.app_key, folder)


class DropboxFinish(BaseModel):
    flow_id: str = Field(max_length=100)
    code: str = Field(min_length=5, max_length=1000)


@router.post("/storage/dropbox/finish")
def finish(body: DropboxFinish):
    result = dropbox.finish(body.flow_id, body.code.strip())
    result["sync_job"] = jobs.enqueue("scan")
    return result


@router.post("/storage/refresh", status_code=202)
def refresh():
    return jobs.enqueue("scan")


@router.get("/reels")
def list_reels(after_id: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200),
               search: str = Query("", max_length=500), status: str | None = None, approved: bool | None = None):
    # Stable keyset pagination, no loading the entire archive into an agent's context.
    where = ["id > ?"]
    args = [after_id]
    if status:
        where.append("status = ?")
        args.append(status)
    if status == 'ready':
        where.append(models.READY_REEL_PREDICATE)
    if approved is not None:
        where.append("approved = ?")
        args.append(int(approved))
    if search:
        where.append("(filename LIKE ? OR quick_summary LIKE ? OR ai_summary LIKE ? OR final_post_text LIKE ? OR quick_tags LIKE ?)")
        args.extend([f"%{search}%"] * 5)
    with get_db_connection() as conn:
        rows = [models.dict_from_row(row) for row in conn.execute(
            f"SELECT * FROM reels WHERE {' AND '.join(where)} ORDER BY id LIMIT ?", (*args, limit + 1))]
    return {"items": rows[:limit], "next_cursor": rows[limit - 1]["id"] if len(rows) > limit else None}


@router.get('/queue/ready', response_model=ReadyQueueResponse)
def ready_queue(after_id: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200),
                platform: str | None = Query(None, pattern=r'^[a-z0-9_-]{1,40}$'),
                account: str | None = Query(None, min_length=1, max_length=200)):
    """Dashboard Ready Queue, across all folders, without reading video bytes.

    Optionally supply platform AND account to omit claimed, uncertain or already
    posted targets. This read is not a reservation: POST /publications to claim.
    """
    if (platform is None) != (account is None):
        raise HTTPException(422, 'Supply both platform and account, or omit both')
    where = ['id > ?', models.READY_REEL_PREDICATE]
    args = [after_id]
    if platform is not None:
        where.append("""NOT EXISTS (SELECT 1 FROM publication_attempts p WHERE p.reel_id=reels.id
            AND p.platform=? AND p.account=? AND (p.status IN ('publishing','uncertain','posted')
                OR (p.status='claimed' AND p.lease_until>=?)))""")
        args.extend([platform, account, time.time()])
    with get_db_connection() as conn:
        rows = [models.dict_from_row(row) for row in conn.execute(
            f"SELECT * FROM reels WHERE {' AND '.join(where)} ORDER BY id LIMIT ?", (*args, limit + 1))]
    return {'items': rows[:limit], 'next_cursor': rows[limit - 1]['id'] if len(rows) > limit else None}


@router.get("/reels/{reel_id}")
def get_reel(reel_id: int):
    reel = models.get_reel_by_id(reel_id)
    if not reel:
        raise HTTPException(404, "Reel not found")
    return reel


@router.post("/reels/{reel_id}/materialize", status_code=202)
def materialize(reel_id: int):
    get_reel(reel_id)
    return jobs.enqueue("materialize", reel_id)


@router.get('/reels/{reel_id}/preview')
def preview_info(reel_id: int):
    """Metadata only. Never downloads or generates a clip."""
    return previews.info(get_reel(reel_id))


@router.post('/reels/{reel_id}/preview', status_code=202)
def request_preview(reel_id: int):
    return previews.enqueue(get_reel(reel_id), requested=True)


@router.get('/reels/{reel_id}/preview/video')
def preview_video(reel_id: int, key: str = Query(pattern=r'^[a-f0-9]{64}$')):
    from fastapi.responses import FileResponse
    path, pinned_key = previews.acquire(get_reel(reel_id), key)

    class PreviewResponse(FileResponse):
        async def __call__(self, scope, receive, send):
            try:
                await super().__call__(scope, receive, send)
            finally:
                previews.release(pinned_key)

    return PreviewResponse(path, media_type='video/mp4')  # AuthMiddleware applies private, no-store.


class PreviewPause(BaseModel):
    paused: bool


@router.post('/previews/pause')
def pause_previews(body: PreviewPause):
    from ..archive import set_state
    set_state('previews_paused', body.paused)
    return previews.status()


@router.post("/reels/{reel_id}/analyze", status_code=202)
def analyze(reel_id: int):
    get_reel(reel_id)
    if not settings.is_gemini_enabled:
        raise HTTPException(400, "Gemini is not configured")
    return jobs.enqueue("analyze", reel_id)


@router.post("/reels/{reel_id}/thumbnail", status_code=202)
def thumbnail(reel_id: int):
    get_reel(reel_id)
    return jobs.enqueue("thumbnail", reel_id)


@router.get("/jobs")
def list_jobs(limit: int = Query(30, ge=1, le=200)):
    with get_db_connection() as conn:
        return {"items": [jobs.serialize(r) for r in conn.execute("SELECT * FROM transfer_jobs ORDER BY created_at DESC LIMIT ?", (limit,))]}


@router.get("/jobs/{job_id}")
def get_job(job_id: str):
    with get_db_connection() as conn:
        row = conn.execute("SELECT * FROM transfer_jobs WHERE id=?", (job_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Job not found")
    return jobs.serialize(row)


@router.get("/reels/{reel_id}/video")
def video(reel_id: int):
    from .reels import video_response
    return video_response(reel_id)


@router.get("/reels/{reel_id}/download")
def download(reel_id: int, source_version: str | None = None):
    from .reels import video_response
    return video_response(reel_id, attachment=True, expected_version=source_version)


class Claim(BaseModel):
    reel_id: int
    platform: str = Field(pattern=r"^[a-z0-9_-]{1,40}$")
    account: str = Field(min_length=1, max_length=200)
    idempotency_key: str = Field(min_length=8, max_length=200)


def expire(conn):
    conn.execute("UPDATE publication_attempts SET status=CASE WHEN status='claimed' THEN 'released' ELSE 'uncertain' END WHERE status IN ('claimed','publishing') AND lease_until < ?", (time.time(),))


@router.post("/publications", status_code=201)
def claim(body: Claim):
    with get_db_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        expire(conn)
        existing = conn.execute("SELECT * FROM publication_attempts WHERE idempotency_key=?", (body.idempotency_key,)).fetchone()
        if existing:
            if (existing["reel_id"], existing["platform"], existing["account"]) != (body.reel_id, body.platform, body.account):
                raise HTTPException(409, "Idempotency key was used for a different request")
            conn.commit()
            return dict(existing)
        reel = conn.execute("SELECT * FROM reels WHERE id=?", (body.reel_id,)).fetchone()
        if not reel:
            raise HTTPException(404, "Reel not found")
        if reel["status"] not in {"ready", "posted"} or not reel["approved"] or not (reel["final_post_text"] or "").strip() or reel["storage_status"] == "missing":
            raise HTTPException(409, "Reel must be approved, ready and available with a final caption")
        active = conn.execute("SELECT id FROM publication_attempts WHERE reel_id=? AND platform=? AND account=? AND status IN ('claimed','publishing','uncertain','posted')", (body.reel_id, body.platform, body.account)).fetchone()
        if active:
            raise HTTPException(409, f"Target already has a publication attempt: {active['id']}")
        key, now = uuid.uuid4().hex, time.time()
        conn.execute("""INSERT INTO publication_attempts VALUES (?,?,?,?,?,'claimed',?,?,?,?,NULL,?,?)""",
                     (key, body.reel_id, body.platform, body.account, body.idempotency_key, reel["source_version"],
                      reel["final_post_text"], reel["hashtags"], now + 900, now, now))
        conn.commit()
        return dict(conn.execute("SELECT * FROM publication_attempts WHERE id=?", (key,)).fetchone())


@router.get("/publications")
def publications(limit: int = Query(50, ge=1, le=200)):
    with get_db_connection() as conn:
        expire(conn)
        conn.commit()
        return {"items": [dict(r) for r in conn.execute("SELECT * FROM publication_attempts ORDER BY created_at DESC LIMIT ?", (limit,))]}


@router.get("/publications/{attempt_id}")
def publication(attempt_id: str):
    with get_db_connection() as conn:
        expire(conn)
        conn.commit()
        row = conn.execute("SELECT * FROM publication_attempts WHERE id=?", (attempt_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Publication attempt not found")
        return dict(row)


class Completion(BaseModel):
    external_id: str = Field(min_length=1, max_length=500, pattern=r'\S')


def completion_receipt(conn, attempt):
    reel = conn.execute('SELECT status,posted_at FROM reels WHERE id=?', (attempt['reel_id'],)).fetchone()
    return dict(attempt) | {'reel_status': reel['status'], 'reel_posted_at': reel['posted_at']}


def transition(attempt_id, action, external_id=None):
    with get_db_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        expire(conn)
        row = conn.execute("SELECT * FROM publication_attempts WHERE id=?", (attempt_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Publication attempt not found")
        state = row["status"]
        target = state
        if action == "complete":
            if state == "posted" and external_id == row["external_id"]:
                conn.commit()
                return completion_receipt(conn, row)
            if state not in {"publishing", "uncertain"}:
                raise HTTPException(409, "Only a started attempt can be completed; do not repeat the external post")
            target = "posted"
        elif action == "release":
            if state not in {"claimed", "released"}:
                raise HTTPException(409, "An external post may exist; reconcile it before retrying")
            target = "released"
        elif state not in {"claimed", "publishing"}:
            raise HTTPException(409, "Lease expired or attempt finished; inspect status before posting")
        elif action == "start":
            reel = conn.execute("SELECT * FROM reels WHERE id=?", (row["reel_id"],)).fetchone()
            if not reel["approved"] or reel["status"] not in {"ready", "posted"} or reel["storage_status"] == "missing" or reel["source_version"] != row["source_version"] or reel["final_post_text"] != row["caption"] or reel["hashtags"] != row["hashtags"]:
                raise HTTPException(409, "Approval, caption or media changed; release this claim and review again")
            if state == "publishing":
                raise HTTPException(409, "Posting already started; reconcile external state instead of posting twice")
            target = "publishing"
        conn.execute("UPDATE publication_attempts SET status=?,lease_until=?,external_id=COALESCE(?,external_id),updated_at=? WHERE id=?",
                     (target, time.time() + 900, external_id, time.time(), attempt_id))
        if action == 'complete':
            stamp = datetime.now(timezone.utc).isoformat()
            # The receipt and Ready -> Posted transition commit together. A late
            # receipt must not consume a newer edit/revision or undo an owner's
            # explicit return to Draft/Archive while the external upload ran.
            conn.execute("""UPDATE reels SET status='posted',posted_at=COALESCE(posted_at,?),updated_at=?
                WHERE id=? AND status IN ('ready','posted') AND source_version IS ?
                    AND final_post_text IS ? AND hashtags IS ?""",
                (stamp, stamp, row['reel_id'], row['source_version'], row['caption'], row['hashtags']))
        conn.commit()
        updated = conn.execute("SELECT * FROM publication_attempts WHERE id=?", (attempt_id,)).fetchone()
        return completion_receipt(conn, updated) if action == 'complete' else dict(updated)


@router.post("/publications/{attempt_id}/renew")
def renew(attempt_id: str):
    return transition(attempt_id, "renew")


@router.post("/publications/{attempt_id}/start")
def start(attempt_id: str):
    return transition(attempt_id, "start")


@router.post("/publications/{attempt_id}/release")
def release(attempt_id: str):
    return transition(attempt_id, "release")


@router.post("/publications/{attempt_id}/complete")
def complete(attempt_id: str, body: Completion):
    return transition(attempt_id, "complete", body.external_id)


class Reconcile(BaseModel):
    outcome: Literal["not_posted", "posted"]
    external_id: str | None = Field(None, max_length=500)


@router.post("/publications/{attempt_id}/reconcile")
def reconcile(attempt_id: str, body: Reconcile):
    # Owner-only escape hatch following manual external-platform inspection.
    if body.outcome == "posted":
        if not body.external_id:
            raise HTTPException(422, "External post ID required")
        return transition(attempt_id, "complete", body.external_id)
    with get_db_connection() as conn:
        conn.execute("UPDATE publication_attempts SET status='released',updated_at=? WHERE id=? AND status='uncertain'", (time.time(), attempt_id))
        conn.commit()
    return publication(attempt_id)
