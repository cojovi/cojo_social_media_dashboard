from datetime import datetime
from typing import List, Optional, Dict, Any
from .database import get_db_connection

# One eligibility rule for the dashboard, counts, legacy queue and agent API.
READY_REEL_PREDICATE = """status='ready' AND approved=1
    AND length(trim(COALESCE(final_post_text,''),char(9)||char(10)||char(13)||' '))>0
    AND storage_status != 'missing'"""

def dict_from_row(row) -> Dict[str, Any]:
    if row is None:
        return None
    d = dict(row)
    # Convert approved to boolean for the API
    d["approved"] = bool(d["approved"])
    return d

def get_all_reels(
    status: Optional[str] = None,
    approved: Optional[bool] = None,
    search: Optional[str] = None,
    has_final_post: Optional[bool] = None,
    has_ai_summary: Optional[bool] = None,
    availability: Optional[str] = None,
    has_quick_summary: Optional[bool] = None
) -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        query = "SELECT * FROM reels WHERE 1=1"
        params = []
        
        if status:
            query += " AND status = ?"
            params.append(status)
            
        if approved is not None:
            query += " AND approved = ?"
            params.append(1 if approved else 0)
            
        if search:
            query += " AND (filename LIKE ? OR filepath LIKE ? OR manual_post_text LIKE ? OR final_post_text LIKE ? OR hashtags LIKE ? OR notes LIKE ? OR ai_summary LIKE ? OR quick_summary LIKE ? OR quick_tags LIKE ? OR quick_category LIKE ?)"
            like_val = f"%{search}%"
            params.extend([like_val] * 10)
            
        if has_final_post is not None:
            if has_final_post:
                query += " AND final_post_text IS NOT NULL AND final_post_text != ''"
            else:
                query += " AND (final_post_text IS NULL OR final_post_text = '')"
                
        if has_ai_summary is not None:
            if has_ai_summary:
                query += " AND ai_summary IS NOT NULL AND ai_summary != ''"
            else:
                query += " AND (ai_summary IS NULL OR ai_summary = '')"
                
        if availability == 'present':
            query += " AND storage_status != 'missing'"
        elif availability:
            query += " AND storage_status = ?"
            params.append(availability)
        if has_quick_summary is not None:
            query += " AND COALESCE(quick_summary, '') " + ("!= ''" if has_quick_summary else "= ''")
        if status == 'ready':
            query += " AND " + READY_REEL_PREDICATE
        # Order by discovered_at descending
        query += " ORDER BY discovered_at DESC, id DESC"
        
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict_from_row(r) for r in rows]

def get_reel_by_id(reel_id: int) -> Optional[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM reels WHERE id = ?", (reel_id,))
        row = cursor.fetchone()
        return dict_from_row(row) if row else None

import unicodedata
import sqlite3

def get_reel_by_filepath(filepath: str) -> Optional[Dict[str, Any]]:
    normalized_path = unicodedata.normalize('NFC', filepath)
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM reels WHERE filepath = ?", (normalized_path,))
        row = cursor.fetchone()
        return dict_from_row(row) if row else None

def upsert_scanned_reel(reel_data: Dict[str, Any]) -> int:
    """
    Inserts a newly scanned reel or updates its system-defined metadata.
    Does NOT overwrite user-facing fields or AI fields.
    """
    now = datetime.now().isoformat()
    # Normalize filepath to NFC
    normalized_filepath = unicodedata.normalize('NFC', reel_data["filepath"])
    reel_data["filepath"] = normalized_filepath
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Check if already exists
        cursor.execute("SELECT id FROM reels WHERE filepath = ?", (normalized_filepath,))
        row = cursor.fetchone()
        
        if row:
            reel_id = row["id"]
            # Update only file-related properties
            cursor.execute(
                """
                UPDATE reels
                SET filename = ?,
                    file_extension = ?,
                    file_size = ?,
                    duration_seconds = ?,
                    created_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    reel_data["filename"],
                    reel_data["file_extension"],
                    reel_data["file_size"],
                    reel_data["duration_seconds"],
                    reel_data["created_at"],
                    now,
                    reel_id
                )
            )
            conn.commit()
            return reel_id
        else:
            try:
                # Insert a completely new reel
                cursor.execute(
                    """
                    INSERT INTO reels (
                        filename, filepath, file_extension, file_size, duration_seconds,
                        thumbnail_path, created_at, updated_at, discovered_at, status, approved
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft', 0)
                    """,
                    (
                        reel_data["filename"],
                        reel_data["filepath"],
                        reel_data["file_extension"],
                        reel_data["file_size"],
                        reel_data["duration_seconds"],
                        reel_data.get("thumbnail_path"),
                        reel_data["created_at"],
                        now,
                        now
                    )
                )
                conn.commit()
                return cursor.lastrowid
            except sqlite3.IntegrityError as e:
                # Safe fallback if concurrent thread inserted it between the SELECT and INSERT
                cursor.execute("SELECT id FROM reels WHERE filepath = ?", (normalized_filepath,))
                fallback_row = cursor.fetchone()
                if fallback_row:
                    reel_id = fallback_row["id"]
                    cursor.execute(
                        """
                        UPDATE reels
                        SET filename = ?,
                            file_extension = ?,
                            file_size = ?,
                            duration_seconds = ?,
                            created_at = ?,
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            reel_data["filename"],
                            reel_data["file_extension"],
                            reel_data["file_size"],
                            reel_data["duration_seconds"],
                            reel_data["created_at"],
                            now,
                            reel_id
                        )
                    )
                    conn.commit()
                    return reel_id
                raise e


def update_reel(reel_id: int, update_data: Dict[str, Any]) -> bool:
    now = datetime.now().isoformat()
    # Fields that user can edit
    allowed_fields = [
        "status", "approved", "manual_post_text", "final_post_text", "hashtags", "notes",
        "ai_summary", "ai_suggested_post_text", "ai_suggested_hashtags", "ai_category",
        "ai_platform_suggestion", "ai_last_analyzed_at", "posted_at", "archived_at", "thumbnail_path", "ai_quality_notes"
    ]
    
    # Filter only allowed and convert boolean to integer for SQLite
    query_fields = []
    params = []
    
    for k, v in update_data.items():
        if k in allowed_fields:
            query_fields.append(f"{k} = ?")
            if k == "approved":
                params.append(1 if v else 0)
            else:
                params.append(v)
                
    if not query_fields:
        return False
        
    query_fields.append("updated_at = ?")
    params.append(now)
    params.append(reel_id)
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        conn.execute("BEGIN IMMEDIATE")
        current = conn.execute("SELECT * FROM reels WHERE id=?", (reel_id,)).fetchone()
        if not current:
            return False
        merged = dict(current) | update_data
        if merged['status'] not in {'draft', 'needs_review', 'ready', 'posted', 'archived'}:
            raise ValueError("Invalid workflow status.")
        if merged['status'] == 'ready' and not (merged.get('final_post_text') or '').strip():
            raise ValueError("Cannot mark reel as ready without final post caption.")
        cursor.execute(f"UPDATE reels SET {', '.join(query_fields)} WHERE id = ?", params)
        conn.commit()
        return cursor.rowcount > 0

def get_ready_queue() -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT * FROM reels 
            WHERE {READY_REEL_PREDICATE}
            ORDER BY updated_at ASC
            """
        )
        rows = cursor.fetchall()
        return [dict_from_row(r) for r in rows]

def get_status_counts() -> Dict[str, int]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status, COUNT(*) as count FROM reels WHERE storage_status != 'missing' GROUP BY status")
        rows = cursor.fetchall()
        
        counts = {
            "all": 0,
            "draft": 0,
            "needs_review": 0,
            "ready": 0,
            "posted": 0,
            "archived": 0
        }
        
        total = 0
        for r in rows:
            status = r["status"]
            count = r["count"]
            if status in counts:
                counts[status] = count
            total += count
            
        counts["all"] = total
        counts["ready"] = conn.execute(f"SELECT COUNT(*) FROM reels WHERE {READY_REEL_PREDICATE}").fetchone()[0]
        return counts


def get_reels_missing_thumbnails(limit: int = 100) -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM reels
            WHERE thumbnail_path IS NULL OR thumbnail_path = ''
            ORDER BY discovered_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [dict_from_row(r) for r in cursor.fetchall()]


def count_reels_missing_thumbnails() -> int:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) AS count FROM reels WHERE thumbnail_path IS NULL OR thumbnail_path = ''"
        )
        row = cursor.fetchone()
        return int(row["count"]) if row else 0
