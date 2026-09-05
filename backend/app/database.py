import sqlite3
from datetime import datetime, timezone
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
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
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
    # Explicit additive migration. Back up a populated pre-migration database first.
    columns = {row[1] for row in conn.execute("PRAGMA table_info(reels)")}
    additions = {
        "storage_status": "TEXT NOT NULL DEFAULT 'unknown'",
        "last_seen_at": "TEXT",
        "source_version": "TEXT",
        "quick_summary": "TEXT",
        "quick_tags": "TEXT",
        "quick_category": "TEXT",
        "quick_summary_source": "TEXT",
        "quick_summary_model": "TEXT",
        "quick_summary_at": "TEXT",
        "ai_quality_notes": "TEXT",
    }
    pending = {k: v for k, v in additions.items() if k not in columns}
    conn.commit()
    if pending and conn.execute("SELECT COUNT(*) FROM reels").fetchone()[0]:
        backup_dir = db_path.parent / "backups"
        backup_dir.mkdir(exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        with sqlite3.connect(backup_dir / f"reelvault-before-archive-{stamp}.db") as backup:
            conn.backup(backup)
    for name, declaration in pending.items():
        conn.execute(f"ALTER TABLE reels ADD COLUMN {name} {declaration}")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS archive_state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS summary_jobs (
            reel_id INTEGER PRIMARY KEY REFERENCES reels(id) ON DELETE CASCADE,
            status TEXT NOT NULL DEFAULT 'queued',
            attempts INTEGER NOT NULL DEFAULT 0,
            available_at REAL NOT NULL DEFAULT 0,
            error TEXT,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ai_usage (
            id INTEGER PRIMARY KEY,
            reel_id INTEGER,
            kind TEXT NOT NULL,
            model TEXT NOT NULL,
            input_tokens INTEGER NOT NULL,
            output_tokens INTEGER NOT NULL,
            estimated_cost_usd REAL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_summary_jobs_pending ON summary_jobs(status, available_at);
        CREATE INDEX IF NOT EXISTS idx_usage_created ON ai_usage(created_at);
        CREATE INDEX IF NOT EXISTS idx_reels_status ON reels(status);
    """)
    conn.execute("PRAGMA user_version=1")
    conn.commit()
    conn.close()

@contextmanager
def get_db_connection():
    db_path = get_db_path()
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row  # enabling dictionary-like access
    try:
        yield conn
    finally:
        conn.close()
