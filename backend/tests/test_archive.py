import io
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from fastapi.testclient import TestClient
from app import archive, models, scanner, quick_summary, icloud
from app.database import get_db_connection, init_db
from app.settings import settings
from app.main import app
from app.usage import record_usage, usage_summary

client = TestClient(app)

@pytest.fixture
def library(tmp_path, monkeypatch, clean_db):
    folder = tmp_path / 'SnapIGTik Download'
    folder.mkdir()
    thumbs = tmp_path / 'thumbnails'
    thumbs.mkdir()
    monkeypatch.setattr(settings, 'REELS_FOLDER', folder)
    monkeypatch.setattr(settings, 'THUMBNAILS_FOLDER', thumbs)
    monkeypatch.setattr(settings, 'FILE_SETTLE_SECONDS', 0)
    return folder


def add_reel(path, thumb=None):
    reel_id = models.upsert_scanned_reel(dict(filename=path.name, filepath=str(path), file_extension='.mp4',
        file_size=42, duration_seconds=10, created_at=datetime.now(timezone.utc).isoformat(), thumbnail_path=thumb))
    return reel_id


def fake_jpeg():
    out = io.BytesIO()
    Image.new('RGB', (300, 600), 'purple').save(out, format='JPEG')
    return out.getvalue()


def enable_worker(monkeypatch):
    monkeypatch.setattr(settings, 'GEMINI_API_KEY', 'test-key')
    monkeypatch.setattr(settings, 'QUICK_SUMMARY_DAILY_BUDGET_USD', 1)
    monkeypatch.setattr(archive, 'summarize_stills', lambda *args: dict(summary='A person installing roof shingles.', category='Construction', tags=['roof', 'shingles']))


def test_scan_recursive_metadata_only_preserves_caption_and_cloud(library, monkeypatch):
    nested = library / 'subfolder'
    nested.mkdir()
    video = nested / 'new.mp4'
    video.write_bytes(b'fake video')
    monkeypatch.setattr(scanner, 'storage_status', lambda p: 'cloud')
    monkeypatch.setattr(scanner, 'get_video_duration', lambda *a: pytest.fail('scan opened video'))
    monkeypatch.setattr(scanner, 'generate_thumbnail', lambda *a: pytest.fail('scan generated thumbnail'))
    assert scanner.scan_reels_folder()['added'] == 1
    reel = models.get_all_reels()[0]
    assert reel['storage_status'] == 'cloud'
    models.update_reel(reel['id'], {'manual_post_text': 'Keep my draft', 'notes': 'Keep notes', 'thumbnail_path': 'missing.jpg'})
    assert scanner.scan_reels_folder()['added'] == 0
    assert models.get_reel_by_id(reel['id'])['manual_post_text'] == 'Keep my draft'
    assert models.get_reel_by_id(reel['id'])['thumbnail_path'] is None
    video.unlink()
    assert scanner.scan_reels_folder()['missing'] == 1
    assert models.get_reel_by_id(reel['id'])['notes'] == 'Keep notes'


def test_missing_root_does_not_create_folder_or_mark_files_missing(library):
    reel_id = add_reel(library / 'old.mp4')
    library.rmdir()
    with pytest.raises(FileNotFoundError):
        scanner.scan_reels_folder()
    assert not library.exists()
    assert models.get_reel_by_id(reel_id)['storage_status'] == 'unknown'


def test_partial_scan_does_not_reconcile_missing(library, monkeypatch):
    reel_id = add_reel(library / 'inaccessible.mp4')
    def walk(folder, onerror, **kwargs):
        onerror(PermissionError('No access'))
        return iter([])
    monkeypatch.setattr(scanner.os, 'walk', walk)
    with pytest.raises(OSError):
        scanner.scan_reels_folder()
    assert models.get_reel_by_id(reel_id)['storage_status'] == 'unknown'


def test_arriving_files_deferred_then_discovered(library, monkeypatch):
    video = library / 'arriving.mp4'
    video.write_bytes(b'partial')
    monkeypatch.setattr(settings, 'FILE_SETTLE_SECONDS', 60)
    assert scanner.scan_reels_folder()['skipped'] == 1
    assert not models.get_all_reels()
    os.utime(video, (time.time()-120, time.time()-120))
    assert scanner.scan_reels_folder()['added'] == 1


def test_legacy_icloud_placeholder_indexed_without_reading(library):
    (library / '.cloud.mp4.icloud').write_bytes(b'placeholder metadata')
    assert scanner.scan_reels_folder()['added'] == 1
    reel = models.get_all_reels()[0]
    assert reel['filename'] == 'cloud.mp4'
    assert reel['storage_status'] == 'cloud'
    assert reel['file_size'] == 0


def test_changed_video_invalidates_only_derived_preview(library):
    video = library / 'replace.mp4'
    video.write_bytes(b'old')
    scanner.scan_reels_folder()
    reel_id = models.get_all_reels()[0]['id']
    models.update_reel(reel_id, {'manual_post_text': 'Keep', 'ai_summary': 'Existing full analysis'})
    with get_db_connection() as conn:
        conn.execute("UPDATE reels SET quick_summary='old description',thumbnail_path='old.jpg' WHERE id=?", (reel_id,))
        conn.commit()
    video.write_bytes(b'changed video')
    scanner.scan_reels_folder()
    reel = models.get_reel_by_id(reel_id)
    assert reel['quick_summary'] is None and reel['thumbnail_path'] is None
    assert reel['manual_post_text'] == 'Keep'
    assert reel['ai_summary'] == 'Existing full analysis'


def test_cloud_cached_thumbnail_does_not_open_video(library, monkeypatch):
    thumb = settings.THUMBNAILS_FOLDER / 'cache.jpg'
    thumb.write_bytes(fake_jpeg())
    reel_id = add_reel(library / 'offloaded.mp4', thumb.name)
    monkeypatch.setattr(quick_summary, 'storage_status', lambda p: 'cloud')
    monkeypatch.setattr(quick_summary.subprocess, 'run', lambda *a, **kw: pytest.fail('opened cloud video'))
    frames, source, _ = quick_summary.prepare_stills(models.get_reel_by_id(reel_id))
    assert len(frames) == 1 and source == 'cached_thumbnail'
    with Image.open(io.BytesIO(frames[0])) as image:
        assert max(image.size) <= 384


def test_cloud_no_thumbnail_defers_and_other_jobs_continue(library, monkeypatch):
    enable_worker(monkeypatch)
    first = add_reel(library / 'available.mp4', 'cache.jpg')
    (settings.THUMBNAILS_FOLDER / 'cache.jpg').write_bytes(fake_jpeg())
    blocked = add_reel(library / 'cloud.mp4')
    archive.enqueue_missing()
    assert archive.process_one()
    assert archive.status()['jobs']['waiting_local'] == 1
    assert archive.process_one()
    assert models.get_reel_by_id(first)['quick_summary']
    assert models.get_reel_by_id(blocked)['quick_summary'] is None


def test_queue_idempotent_and_recovers_expired_lease(library, monkeypatch):
    enable_worker(monkeypatch)
    reel_id = add_reel(library / 'cloud.mp4', 'cache.jpg')
    (settings.THUMBNAILS_FOLDER / 'cache.jpg').write_bytes(fake_jpeg())
    models.update_reel(reel_id, {'manual_post_text': 'User caption', 'hashtags': '#user'})
    assert archive.enqueue_missing() == 1
    assert archive.enqueue_missing() == 0
    with get_db_connection() as conn:
        conn.execute("UPDATE summary_jobs SET status='processing', available_at=0")
        conn.commit()
    assert archive.process_one()
    reel = models.get_reel_by_id(reel_id)
    assert reel['manual_post_text'] == 'User caption' and reel['hashtags'] == '#user'
    assert reel['quick_summary_source'] == 'cached_thumbnail'
    assert archive.enqueue_missing() == 0
    assert models.get_all_reels(search='shingles')[0]['id'] == reel_id


def test_daily_budget_pause_and_unknown_model_never_call_provider(library, monkeypatch):
    enable_worker(monkeypatch)
    add_reel(library / 'video.mp4')
    archive.enqueue_missing()
    monkeypatch.setattr(archive, 'prepare_stills', lambda *a: pytest.fail('budget should stop before file access'))
    archive.set_state('paused', True)
    assert archive.process_one() is False
    archive.set_state('paused', False)
    monkeypatch.setattr(settings, 'QUICK_SUMMARY_DAILY_BUDGET_USD', 0)
    assert archive.process_one() is False
    monkeypatch.setattr(settings, 'QUICK_SUMMARY_DAILY_BUDGET_USD', 1)
    monkeypatch.setattr(settings, 'QUICK_SUMMARY_MODEL', 'unknown-model')
    assert archive.process_one() is False


def test_failed_requests_have_bounded_retries(library, monkeypatch):
    enable_worker(monkeypatch)
    add_reel(library / 'broken.mp4')
    archive.enqueue_missing()
    def fail(*a): raise RuntimeError('Corrupt video')
    monkeypatch.setattr(archive, 'prepare_stills', fail)
    for _ in range(3):
        assert archive.process_one()
        with get_db_connection() as conn:
            conn.execute('UPDATE summary_jobs SET available_at=0')
            conn.commit()
    assert archive.status()['jobs']['failed'] == 1
    assert archive.process_one() is False
    assert archive.enqueue_missing(retry=True) == 1


def test_usage_accounts_for_thoughts_and_audio(clean_db):
    usage = SimpleNamespace(prompt_token_count=1000, candidates_token_count=100, thoughts_token_count=100,
                            prompt_tokens_details=[SimpleNamespace(modality='AUDIO', token_count=100)])
    record_usage(1, 'full', 'gemini-2.5-flash', usage)
    result = usage_summary()
    assert result['output_tokens'] == 200
    assert result['estimated_cost_usd'] == pytest.approx(0.00087)


def test_ready_patch_and_queue_reject_blank_and_missing(library):
    reel_id = add_reel(library / 'v.mp4')
    response = client.patch(f'/api/reels/{reel_id}', json={'status':'ready','final_post_text':' \n\t'})
    assert response.status_code == 400
    assert client.patch(f'/api/reels/{reel_id}', json={'status':'nonsense'}).status_code == 400
    models.update_reel(reel_id, {'status':'ready','approved':True,'final_post_text':'Ready caption'})
    assert len(models.get_ready_queue()) == 1
    with get_db_connection() as conn:
        conn.execute("UPDATE reels SET storage_status='missing' WHERE id=?", (reel_id,))
        conn.commit()
    assert models.get_ready_queue() == []
    assert client.get('/api/reels?status=ready').json() == []


def test_dataless_detection_works_without_foundation(tmp_path, monkeypatch):
    monkeypatch.setattr(icloud, 'HAS_FOUNDATION', False)
    monkeypatch.setattr(icloud.os, 'stat', lambda p: SimpleNamespace(st_flags=icloud.SF_DATALESS))
    assert icloud.storage_status('/cloud/video.mp4') == 'cloud'
    assert not icloud.is_icloud_file_downloaded('/cloud/video.mp4')


def test_worker_scans_on_startup_and_periodically(library, monkeypatch):
    called = threading.Event()
    calls = []
    def scan(): calls.append(1); called.set()
    monkeypatch.setattr(archive, 'run_scan', scan)
    monkeypatch.setattr(archive, 'process_one', lambda: False)
    monkeypatch.setattr(settings, 'AUTO_SCAN', True)
    monkeypatch.setattr(settings, 'SCAN_INTERVAL_SECONDS', 0.03)
    worker = archive.ArchiveWorker()
    worker.start()
    try:
        assert called.wait(1)
        called.clear()
        assert called.wait(1)
    finally:
        worker.stop()
    assert len(calls) >= 2


def test_migration_backs_up_and_preserves_legacy_data(tmp_path, monkeypatch):
    db = tmp_path / 'legacy.db'
    # An old database from the original release, with saved editorial data.
    sql = """CREATE TABLE reels (
        id INTEGER PRIMARY KEY, filename TEXT NOT NULL, filepath TEXT UNIQUE NOT NULL,
        file_extension TEXT NOT NULL, file_size INTEGER NOT NULL, duration_seconds REAL NOT NULL,
        thumbnail_path TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, discovered_at TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'draft', approved INTEGER NOT NULL DEFAULT 0,
        manual_post_text TEXT, final_post_text TEXT, hashtags TEXT, notes TEXT, ai_summary TEXT,
        ai_suggested_post_text TEXT, ai_suggested_hashtags TEXT, ai_category TEXT,
        ai_platform_suggestion TEXT, ai_last_analyzed_at TEXT, posted_at TEXT, archived_at TEXT)"""
    with sqlite3.connect(db) as conn:
        conn.execute(sql)
        conn.execute("""INSERT INTO reels (filename,filepath,file_extension,file_size,duration_seconds,
            created_at,updated_at,discovered_at,manual_post_text) VALUES ('v.mp4','/v.mp4','.mp4',10,2,'now','now','now','Saved caption')""")
    monkeypatch.setattr(settings, 'DATABASE_PATH', db)
    init_db()
    init_db()
    with get_db_connection() as conn:
        row = dict(conn.execute('SELECT * FROM reels').fetchone())
    assert row['manual_post_text'] == 'Saved caption' and row['storage_status'] == 'unknown'
    backups = list((tmp_path/'backups').glob('*.db'))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as backup:
        assert backup.execute('SELECT manual_post_text FROM reels').fetchone()[0] == 'Saved caption'


def test_queue_concurrent_claims_only_analyze_once(library, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    enable_worker(monkeypatch)
    add_reel(library / 'cloud.mp4', 'cache.jpg')
    (settings.THUMBNAILS_FOLDER / 'cache.jpg').write_bytes(fake_jpeg())
    archive.enqueue_missing()
    calls = []
    def describe(*args):
        calls.append(1)
        time.sleep(0.04)
        return dict(summary='Test summary', category='Test', tags=['test'])
    monkeypatch.setattr(archive, 'summarize_stills', describe)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: archive.process_one(), range(2)))
    assert sum(results) == 1 and len(calls) == 1


def test_cache_description_retains_output_budget_and_bills_invalid_json(library, monkeypatch):
    from google import genai
    enable_worker(monkeypatch)
    usage = SimpleNamespace(prompt_token_count=900, candidates_token_count=80, thoughts_token_count=0, prompt_tokens_details=[])
    class FakeClient:
        def __init__(self, **kwargs): self.models = self
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def generate_content(self, **kwargs):
            assert kwargs['model'] == 'gemini-2.5-flash-lite'
            assert kwargs['config'].thinking_config.thinking_budget == 0
            assert kwargs['config'].max_output_tokens == 256
            assert len(kwargs['contents']) == 2  # One cached image and one prompt.
            return SimpleNamespace(text='invalid JSON', usage_metadata=usage)
    monkeypatch.setattr(genai, 'Client', FakeClient)
    with pytest.raises(ValueError):
        quick_summary.summarize_stills(1, [fake_jpeg()], 'cached_thumbnail')
    assert usage_summary()['requests'] == 1


def test_hydration_timeout_surfaces_as_503(library, monkeypatch):
    from app.routes import reels
    video = library / 'video.mp4'
    video.write_bytes(b'video')
    reel_id = add_reel(video)
    monkeypatch.setattr(reels, 'ensure_icloud_downloaded', lambda *a, **kw: False)
    assert client.get(f'/api/reels/{reel_id}/video').status_code == 503


def test_parse_invalid_fenced_response_does_not_crash():
    from app.gemini_service import parse_ai_json, GeminiServiceError
    with pytest.raises(GeminiServiceError):
        parse_ai_json('```')


def test_hidden_subfolders_are_scanned_and_ties_sort_newest_first(library):
    nested = library / '.saved'
    nested.mkdir()
    (nested/'one.mp4').write_bytes(b'first')
    (nested/'two.mp4').write_bytes(b'second')
    assert scanner.scan_reels_folder()['added'] == 2
    reels = models.get_all_reels()
    assert reels[0]['discovered_at'] == reels[1]['discovered_at']
    assert reels[0]['id'] > reels[1]['id']
