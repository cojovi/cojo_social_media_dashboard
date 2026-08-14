from fastapi import APIRouter
from pathlib import Path
from ..schemas import HealthResponse
from ..settings import settings

router = APIRouter(prefix="/health", tags=["health"])

@router.get("", response_model=HealthResponse)
def health_check():
    reels_path = Path(settings.REELS_FOLDER)
    db_path = Path(settings.DATABASE_PATH)
    thumbs_path = Path(settings.THUMBNAILS_FOLDER)
    
    return {
        "status": "ok",
        "gemini_configured": settings.is_gemini_enabled,
        "gemini_model": settings.GEMINI_MODEL,
        "reels_folder_configured": reels_path.exists(),
        "reels_folder_path": str(reels_path.resolve()),
        "db_path": str(db_path.resolve()),
        "thumbnails_folder_path": str(thumbs_path.resolve())
    }
