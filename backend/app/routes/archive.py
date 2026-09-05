from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from .. import archive
from ..settings import settings

router = APIRouter(prefix='/archive', tags=['archive'])

class DescribeRequest(BaseModel):
    reel_ids: list[int] | None = Field(default=None, max_length=10000)
    retry: bool = False

class PauseRequest(BaseModel):
    paused: bool

@router.get('')
def archive_status():
    return archive.status()

@router.post('/describe')
def describe_missing(payload: DescribeRequest):
    if not settings.is_gemini_enabled:
        raise HTTPException(400, 'Configure GEMINI_API_KEY to generate quick descriptions.')
    count = archive.enqueue_missing(payload.reel_ids, retry=payload.retry)
    return {'queued': count}

@router.post('/pause')
def pause_descriptions(payload: PauseRequest):
    archive.set_state('paused', payload.paused)
    return {'paused': payload.paused}
