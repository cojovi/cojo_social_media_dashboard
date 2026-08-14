import pytest
from pathlib import Path
from datetime import datetime
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_db_connection
from app.settings import Settings, settings
from app import models
from app.scanner import scan_reels_folder
from app.gemini_service import analyze_video_with_gemini, GeminiServiceError

client = TestClient(app)

def test_database_creation():
    """
    1. Database creation test. Verifies that the 'reels' table was created successfully
    with all expected columns.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(reels)")
        columns = {row["name"] for row in cursor.fetchall()}
        
    expected_fields = {
        "id", "filename", "filepath", "file_extension", "file_size",
        "duration_seconds", "thumbnail_path", "created_at", "updated_at",
        "discovered_at", "status", "approved", "manual_post_text",
        "final_post_text", "hashtags", "notes", "ai_summary",
        "ai_suggested_post_text", "ai_suggested_hashtags", "ai_category",
        "ai_platform_suggestion", "ai_last_analyzed_at", "posted_at",
        "archived_at"
    }
    assert expected_fields.issubset(columns), f"Missing fields: {expected_fields - columns}"

def test_scanning_folder(clean_db):
    """
    2. Directory crawling test. Creates a mock video file, runs the scanner,
    and asserts the video is indexed correctly in SQLite without duplicating.
    """
    # Verify DB is currently clean
    all_reels = models.get_all_reels()
    assert len(all_reels) == 0
    
    # Create a mock video file in the test reels folder
    reels_dir = Path(settings.REELS_FOLDER)
    mock_video_path = reels_dir / "roofing_project_1.mp4"
    with open(mock_video_path, "wb") as f:
        f.write(b"MOCK_MP4_VIDEO_CONTENT")
        
    # Trigger scanner
    scan_stats = scan_reels_folder()
    assert scan_stats["scanned"] == 1
    assert scan_stats["added"] == 1
    assert scan_stats["updated"] == 0
    
    # Assert database entry
    db_reels = models.get_all_reels()
    assert len(db_reels) == 1
    reel = db_reels[0]
    assert reel["filename"] == "roofing_project_1.mp4"
    assert reel["file_extension"] == ".mp4"
    assert reel["file_size"] == len("MOCK_MP4_VIDEO_CONTENT")
    assert reel["status"] == "draft"
    assert reel["approved"] is False
    
    # Rescan folder with no changes, should update stats but not double-add
    scan_stats2 = scan_reels_folder()
    assert scan_stats2["scanned"] == 1
    assert scan_stats2["added"] == 0
    assert scan_stats2["updated"] == 1
    
    # Verify no duplication
    assert len(models.get_all_reels()) == 1

def test_updating_reel_fields(clean_db):
    """
    3. Test modifying editable reel fields in SQLite.
    """
    reel_id = models.upsert_scanned_reel({
        "filename": "test_reel.mp4",
        "filepath": "/mock/path/test_reel.mp4",
        "file_extension": ".mp4",
        "file_size": 1024,
        "duration_seconds": 12.5,
        "created_at": datetime.now().isoformat()
    })
    
    # Update fields
    update_payload = {
        "manual_post_text": "Manual caption writing",
        "hashtags": "#roofing #workmanship",
        "notes": "Important company update"
    }
    success = models.update_reel(reel_id, update_payload)
    assert success is True
    
    # Assert updates persisted
    reel = models.get_reel_by_id(reel_id)
    assert reel["manual_post_text"] == "Manual caption writing"
    assert reel["hashtags"] == "#roofing #workmanship"
    assert reel["notes"] == "Important company update"

def test_ready_queue_validation(clean_db):
    """
    4. Ready Queue validation test. Verifies a reel cannot be approved/marked ready
    without a valid final post caption text, but succeeds when caption exists.
    """
    # 1. Add mock scanned reel to DB
    reel_id = models.upsert_scanned_reel({
        "filename": "test_ready_reel.mp4",
        "filepath": "/mock/path/test_ready_reel.mp4",
        "file_extension": ".mp4",
        "file_size": 2048,
        "duration_seconds": 15.0,
        "created_at": datetime.now().isoformat()
    })
    
    # 2. Try marking ready via API when final_post_text is empty, should fail with 400 Validation Error
    response = client.post(f"/api/reels/{reel_id}/mark-ready")
    assert response.status_code == 400
    assert "Cannot mark reel as ready without final post caption" in response.json()["detail"]
    
    # Verify status in database remains 'draft'
    reel = models.get_reel_by_id(reel_id)
    assert reel["status"] == "draft"
    assert reel["approved"] is False
    
    # 3. Add valid final post text
    models.update_reel(reel_id, {"final_post_text": "This is our amazing completed roofing project!"})
    
    # 4. Try marking ready again, should succeed
    response = client.post(f"/api/reels/{reel_id}/mark-ready")
    assert response.status_code == 200
    
    # Verify status changed and approved
    reel = models.get_reel_by_id(reel_id)
    assert reel["status"] == "ready"
    assert reel["approved"] is True
    
    # 5. Check `/api/queue/ready` contains this reel
    response = client.get("/api/queue/ready")
    assert response.status_code == 200
    queue = response.json()
    assert len(queue) == 1
    assert queue[0]["id"] == reel_id
    assert queue[0]["final_post_text"] == "This is our amazing completed roofing project!"

def test_gemini_disabled_behavior():
    """
    5. Test Gemini-disabled behavior. Since GEMINI_API_KEY is unset in test config,
    any attempt to execute AI analysis should fail gracefully.
    """
    assert settings.is_gemini_enabled is False
    
    with pytest.raises(GeminiServiceError) as exc_info:
        analyze_video_with_gemini("/mock/video.mp4")
    assert "Gemini API key is not configured" in str(exc_info.value)
    
    # Also verify route returns a 400 Bad Request error rather than crashing the server
    response = client.post("/api/reels/999/analyze")
    assert response.status_code in (400, 404)  # 404 if reel doesn't exist, 400 if service error

def test_legacy_gemini_model_is_normalized(monkeypatch):
    """
    6. Legacy Gemini model configuration should be upgraded automatically
    to a currently supported default so older .env files do not break.
    """
    monkeypatch.setenv("GEMINI_MODEL", "gemini-1.5-pro")

    refreshed_settings = Settings()

    assert refreshed_settings.GEMINI_MODEL == "gemini-2.5-flash"
