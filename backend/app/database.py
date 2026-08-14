import sqlite3
import os
from contextlib import contextmanager
from pathlib import Path
from .settings import settings

def get_db_path() -> Path:
    # Ensure database parent directory exists
    db_path = Path(settings.DATABASE_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path

def init_db():
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create the reels table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT NOT NULL,
        filepath TEXT UNIQUE NOT NULL,
        file_extension TEXT NOT NULL,
        file_size INTEGER NOT NULL,
        duration_seconds REAL NOT NULL,
        thumbnail_path TEXT,
        created_at TEXT NOT NULL,       -- file creation/modification timestamp
        updated_at TEXT NOT NULL,       -- DB entry update time
        discovered_at TEXT NOT NULL,    -- scan insert time
        status TEXT NOT NULL DEFAULT 'draft',
        approved INTEGER NOT NULL DEFAULT 0, -- 0 = false, 1 = true
        manual_post_text TEXT,
        final_post_text TEXT,
        hashtags TEXT,
        notes TEXT,
        ai_summary TEXT,
        ai_suggested_post_text TEXT,
        ai_suggested_hashtags TEXT,
        ai_category TEXT,
        ai_platform_suggestion TEXT,
        ai_last_analyzed_at TEXT,
        posted_at TEXT,
        archived_at TEXT
    )
    """)
    conn.commit()
    conn.close()

@contextmanager
def get_db_connection():
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # enabling dictionary-like access
    try:
        yield conn
    finally:
        conn.close()
