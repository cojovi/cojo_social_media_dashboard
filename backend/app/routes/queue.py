from fastapi import APIRouter, HTTPException
from typing import List
from ..schemas import ReelResponse
from .. import models

router = APIRouter(prefix="/queue", tags=["queue"])

@router.get("/ready", response_model=List[ReelResponse])
def get_ready_queue():
    """
    Returns only reels that are approved, set to status 'ready', and have a valid final caption.
    This queue is designed to be polled safely by future automated posting agents.
    """
    try:
        queue = models.get_ready_queue()
        return queue
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error reading ready queue: {e}")
