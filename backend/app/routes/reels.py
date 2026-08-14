from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from typing import List, Optional, Dict, Any
from datetime import datetime

from ..schemas import ReelResponse, ReelUpdate, ScanResponse, StatusCountsResponse, ThumbnailBackfillResponse
from .. import models
from ..scanner import scan_reels_folder, backfill_thumbnails
from ..thumbnails import ensure_thumbnail_for_video
from ..icloud import ensure_icloud_downloaded
from ..gemini_service import analyze_video_with_gemini, GeminiServiceError

router = APIRouter(prefix="/reels", tags=["reels"])

@router.post("/scan", response_model=ScanResponse)
def trigger_scan():
    """
    Scans the local reels folder and synchronizes it with the SQLite database.
    Does not duplicate files. Extracts metadata and makes thumbnails.
    """
    try:
        stats = scan_reels_folder()
        return {
            "status": "success",
            "scanned_count": stats["scanned"],
            "added_count": stats["added"],
            "updated_count": stats["updated"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Directory scanning failed: {e}")

@router.get("/stats", response_model=StatusCountsResponse)
def get_reels_stats():
    """
    Returns breakdown counts for each reel status (draft, needs_review, ready, posted, archived).
    """
    try:
        return models.get_status_counts()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch stats: {e}")

@router.get("", response_model=List[ReelResponse])
def get_reels(
    status: Optional[str] = Query(None, description="Filter by status (draft, ready, etc.)"),
    approved: Optional[bool] = Query(None, description="Filter by approved status"),
    search: Optional[str] = Query(None, description="Search term in filename/captions/hashtags"),
    has_final_post: Optional[bool] = Query(None, description="Filter by final caption presence"),
    has_ai_summary: Optional[bool] = Query(None, description="Filter by AI analysis completion")
):
    """
    Retrieves all indexed reels matching optional filter and search terms.
    """
    try:
        return models.get_all_reels(
            status=status,
            approved=approved,
            search=search,
            has_final_post=has_final_post,
            has_ai_summary=has_ai_summary
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list reels: {e}")

@router.post("/thumbnails/backfill", response_model=ThumbnailBackfillResponse)
def trigger_thumbnail_backfill(
    limit: int = Query(15, ge=1, le=30, description="Max reels to process this batch"),
):
    """
    Generate thumbnails for reels missing them.
    Pulls each file from iCloud on demand — not a full-library download.
    """
    try:
        return backfill_thumbnails(limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Thumbnail backfill failed: {e}")

from fastapi.responses import FileResponse
from pathlib import Path

@router.get("/{reel_id}", response_model=ReelResponse)
def get_reel(reel_id: int):
    """
    Fetches a single reel by its primary database ID.
    """
    reel = models.get_reel_by_id(reel_id)
    if not reel:
        raise HTTPException(status_code=404, detail="Reel not found.")
    return reel

@router.post("/{reel_id}/thumbnail", response_model=ReelResponse)
def generate_single_thumbnail(reel_id: int):
    """Generate (or regenerate) thumbnail for one reel, fetching from iCloud if needed."""
    reel = models.get_reel_by_id(reel_id)
    if not reel:
        raise HTTPException(status_code=404, detail="Reel not found.")

    thumb_path = ensure_thumbnail_for_video(reel["filepath"])
    if not thumb_path:
        raise HTTPException(
            status_code=400,
            detail="Could not generate thumbnail. File may still be in iCloud — try Quick Look first.",
        )

    models.update_reel(reel_id, {"thumbnail_path": Path(thumb_path).name})
    return models.get_reel_by_id(reel_id)

@router.get("/{reel_id}/video")
def stream_reel_video(reel_id: int):
    """
    Streams the local video file for standard HTML5 playback.
    Handles Byte-Ranges for media seeking automatically.
    """
    reel = models.get_reel_by_id(reel_id)
    if not reel:
        raise HTTPException(status_code=404, detail="Reel not found.")
    
    filepath = reel["filepath"]
    if not Path(filepath).exists():
        raise HTTPException(status_code=404, detail="Video file does not exist locally.")
        
    return FileResponse(filepath)

@router.patch("/{reel_id}", response_model=ReelResponse)
def update_reel_fields(reel_id: int, payload: ReelUpdate):
    """
    Updates editable fields of a reel.
    """
    reel = models.get_reel_by_id(reel_id)
    if not reel:
        raise HTTPException(status_code=404, detail="Reel not found.")
        
    update_dict = payload.model_dump(exclude_unset=True)
    if not update_dict:
        return reel
        
    try:
        success = models.update_reel(reel_id, update_dict)
        if not success:
            raise HTTPException(status_code=400, detail="Failed to save update.")
        return models.get_reel_by_id(reel_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error writing updates: {e}")

@router.post("/{reel_id}/analyze", response_model=ReelResponse)
def run_ai_analysis(reel_id: int):
    """
    Triggers Gemini Files API upload and analysis for copywriting & summaries.
    Saves suggestions without overwriting user manual inputs.
    """
    reel = models.get_reel_by_id(reel_id)
    if not reel:
        raise HTTPException(status_code=404, detail="Reel not found.")
        
    try:
        if not ensure_icloud_downloaded(reel["filepath"], timeout=120.0):
            raise HTTPException(
                status_code=400,
                detail="Video is not available locally yet. Open Quick Look first or wait for iCloud to download.",
            )

        analysis = analyze_video_with_gemini(reel["filepath"])
        
        # Format tags as string if list is returned
        tags_list = analysis.get("hashtags", [])
        tags_str = " ".join(tags_list) if isinstance(tags_list, list) else str(tags_list)
        
        update_data = {
            "ai_summary": analysis.get("summary", ""),
            "ai_suggested_post_text": analysis.get("suggested_post", ""),
            "ai_suggested_hashtags": tags_str,
            "ai_category": analysis.get("category", "Showcase"),
            "ai_platform_suggestion": analysis.get("platform_suggestion", "Instagram"),
            "ai_last_analyzed_at": datetime.now().isoformat()
        }
        
        models.update_reel(reel_id, update_data)
        return models.get_reel_by_id(reel_id)
        
    except GeminiServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI analysis execution failed: {e}")

@router.post("/{reel_id}/use-ai-caption", response_model=ReelResponse)
def copy_ai_caption(reel_id: int):
    """
    Copies Gemini's suggested post text into final_post_text.
    """
    reel = models.get_reel_by_id(reel_id)
    if not reel:
        raise HTTPException(status_code=404, detail="Reel not found.")
        
    if not reel.get("ai_suggested_post_text"):
        raise HTTPException(status_code=400, detail="No AI suggested caption exists. Run analysis first.")
        
    models.update_reel(reel_id, {"final_post_text": reel["ai_suggested_post_text"]})
    return models.get_reel_by_id(reel_id)

@router.post("/{reel_id}/use-ai-hashtags", response_model=ReelResponse)
def copy_ai_hashtags(reel_id: int):
    """
    Copies Gemini's suggested hashtags into the hashtags field.
    """
    reel = models.get_reel_by_id(reel_id)
    if not reel:
        raise HTTPException(status_code=404, detail="Reel not found.")
        
    if not reel.get("ai_suggested_hashtags"):
        raise HTTPException(status_code=400, detail="No AI suggested hashtags exist. Run analysis first.")
        
    models.update_reel(reel_id, {"hashtags": reel["ai_suggested_hashtags"]})
    return models.get_reel_by_id(reel_id)

@router.post("/{reel_id}/mark-ready", response_model=ReelResponse)
def mark_reel_ready(reel_id: int):
    """
    Approves and marks a reel as 'ready'. Requires a valid non-empty final_post_text.
    """
    reel = models.get_reel_by_id(reel_id)
    if not reel:
        raise HTTPException(status_code=404, detail="Reel not found.")
        
    final_post = reel.get("final_post_text") or ""
    if not final_post.strip():
        raise HTTPException(
            status_code=400, 
            detail="Cannot mark reel as ready without final post caption. Please prewrite or use the AI caption first."
        )
        
    models.update_reel(reel_id, {
        "status": "ready",
        "approved": True
    })
    return models.get_reel_by_id(reel_id)

@router.post("/{reel_id}/mark-posted", response_model=ReelResponse)
def mark_reel_posted(reel_id: int):
    """
    Sets status of reel to 'posted' and saves posted_at timestamp.
    """
    reel = models.get_reel_by_id(reel_id)
    if not reel:
        raise HTTPException(status_code=404, detail="Reel not found.")
        
    models.update_reel(reel_id, {
        "status": "posted",
        "posted_at": datetime.now().isoformat()
    })
    return models.get_reel_by_id(reel_id)

@router.post("/{reel_id}/archive", response_model=ReelResponse)
def archive_reel(reel_id: int):
    """
    Sets status of reel to 'archived' and saves archived_at timestamp.
    """
    reel = models.get_reel_by_id(reel_id)
    if not reel:
        raise HTTPException(status_code=404, detail="Reel not found.")
        
    models.update_reel(reel_id, {
        "status": "archived",
        "archived_at": datetime.now().isoformat()
    })
    return models.get_reel_by_id(reel_id)
