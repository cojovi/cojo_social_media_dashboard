from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any

class ReelResponse(BaseModel):
    id: int
    filename: str
    filepath: str
    file_extension: str
    file_size: int
    duration_seconds: float
    thumbnail_path: Optional[str] = None
    created_at: str
    updated_at: str
    discovered_at: str
    status: str
    approved: bool
    manual_post_text: Optional[str] = None
    final_post_text: Optional[str] = None
    hashtags: Optional[str] = None
    notes: Optional[str] = None
    ai_summary: Optional[str] = None
    ai_suggested_post_text: Optional[str] = None
    ai_suggested_hashtags: Optional[str] = None
    ai_category: Optional[str] = None
    ai_platform_suggestion: Optional[str] = None
    ai_last_analyzed_at: Optional[str] = None
    posted_at: Optional[str] = None
    archived_at: Optional[str] = None

    storage_status: str = 'unknown'
    last_seen_at: Optional[str] = None
    source_version: Optional[str] = None
    quick_summary: Optional[str] = None
    quick_tags: Optional[str] = None
    quick_category: Optional[str] = None
    quick_summary_source: Optional[str] = None
    quick_summary_model: Optional[str] = None
    quick_summary_at: Optional[str] = None
    ai_quality_notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class ReelUpdate(BaseModel):
    status: Optional[str] = None
    approved: Optional[bool] = None
    manual_post_text: Optional[str] = None
    final_post_text: Optional[str] = None
    hashtags: Optional[str] = None
    notes: Optional[str] = None
    ai_summary: Optional[str] = None
    ai_suggested_post_text: Optional[str] = None
    ai_suggested_hashtags: Optional[str] = None
    ai_category: Optional[str] = None
    ai_platform_suggestion: Optional[str] = None
    posted_at: Optional[str] = None
    archived_at: Optional[str] = None
    thumbnail_path: Optional[str] = None

class StatusCountsResponse(BaseModel):
    all: int
    draft: int
    needs_review: int
    ready: int
    posted: int
    archived: int

class HealthResponse(BaseModel):
    status: str
    gemini_configured: bool
    gemini_model: str
    reels_folder_configured: bool
    reels_folder_path: str
    db_path: str
    thumbnails_folder_path: str

class ScanResponse(BaseModel):
    status: str
    scanned_count: int
    added_count: int
    updated_count: int
    missing_count: int = 0
    skipped_count: int = 0

class ThumbnailBackfillResponse(BaseModel):
    processed: int
    generated: int
    failed: int
    remaining: int
