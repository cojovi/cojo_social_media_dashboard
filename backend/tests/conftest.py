import os
import shutil
import tempfile
from pathlib import Path
import pytest

# Ensure safe isolated folders are set in environment BEFORE importing settings
test_dir = Path(tempfile.mkdtemp(prefix="reelvault_test_"))
test_db_path = test_dir / "test_reelvault.db"
test_reels_folder = test_dir / "reels"
test_thumbnails_folder = test_dir / "thumbnails"

test_reels_folder.mkdir(parents=True, exist_ok=True)
test_thumbnails_folder.mkdir(parents=True, exist_ok=True)

os.environ["DATABASE_PATH"] = str(test_db_path)
os.environ["REELS_FOLDER"] = str(test_reels_folder)
os.environ["THUMBNAILS_FOLDER"] = str(test_thumbnails_folder)
os.environ["AUTO_SCAN"] = "false"
os.environ["AUTO_QUICK_SUMMARY"] = "false"
os.environ["FILE_SETTLE_SECONDS"] = "0"
os.environ["GEMINI_API_KEY"] = ""  # Force empty API key to test offline mode

from app.database import init_db
from app.settings import settings

@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    # Initialize the test SQLite database
    init_db()
    yield
    # Clean up test directories
    if test_dir.exists():
        shutil.rmtree(test_dir)

@pytest.fixture
def clean_db():
    import sqlite3
    # Helper to clear table rows before each test if desired
    from app.database import get_db_connection
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM reels")
        cursor.execute("DELETE FROM summary_jobs")
        cursor.execute("DELETE FROM archive_state")
        cursor.execute("DELETE FROM ai_usage")
        conn.commit()
    yield
