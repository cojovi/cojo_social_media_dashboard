"""Folder reconciliation through the same scan entry point the dashboard uses."""
import pytest
from fastapi.testclient import TestClient

from app import archive, models
from app.database import get_db_connection
from app.dropbox_storage import dropbox, StorageError
from app.main import app
from app.settings import settings

client = TestClient(app)


def video(file_id, path, rev='unchanged'):
    return {'.tag': 'file', 'id': file_id, 'name': path.rsplit('/', 1)[-1],
            'path_lower': path.lower(), 'path_display': path, 'rev': rev,
            'size': 10, 'server_modified': '2026-09-01T00:00:00Z',
            'content_hash': 'a' * 64}


@pytest.fixture
def source(clean_db, monkeypatch):
    monkeypatch.setattr(settings, 'STORAGE_PROVIDER', 'dropbox')
    snapshot = [video('id:one', '/archive/SnapIGTik Download/original.mp4'),
                video('id:two', '/archive/SnapIGTik Download/delete.mp4')]
    def changes(cursor):
        assert cursor is None, 'Every rescan must reconcile a fresh tree, including existing stale paths'
        return list(snapshot), 'fresh-cursor', True
    monkeypatch.setattr(dropbox, 'changes', changes)
    assert client.post('/api/reels/scan').status_code == 200
    return snapshot


def test_rescan_moves_and_renames_same_record_preserving_work(source):
    original = next(r for r in models.get_all_reels() if r['provider_id'] == 'id:one')
    models.update_reel(original['id'], {'manual_post_text': 'My draft', 'final_post_text': 'My caption',
                                      'notes': 'My notes', 'approved': True, 'status': 'ready'})
    with get_db_connection() as conn:
        conn.execute("UPDATE reels SET quick_summary='Saved description',thumbnail_path='cached.jpg' WHERE id=?", (original['id'],))
        conn.execute("INSERT INTO summary_jobs(reel_id,status,updated_at) VALUES (?,'done','now')", (original['id'],))
        conn.commit()
    for path in ['/archive/SnapIGTik Download/artistic/original.mp4',
                 '/archive/SnapIGTik Download/artistic/renamed.mp4',
                 '/archive/other/renamed.mp4']:
        source[0] = video('id:one', path)
        response = client.post('/api/reels/scan')
        assert response.status_code == 200
        assert response.json()['moved_count'] == 1
        assert response.json()['added_count'] == 0
        current = models.get_reel_by_id(original['id'])
        assert current['filepath'] == 'dropbox:' + path
        assert current['filename'] == path.rsplit('/', 1)[-1]
        assert current['manual_post_text'] == 'My draft' and current['notes'] == 'My notes'
        assert current['final_post_text'] == 'My caption' and current['approved'] and current['status'] == 'ready'
        assert current['quick_summary'] == 'Saved description' and current['thumbnail_path'] == 'cached.jpg'
        with get_db_connection() as conn:
            assert conn.execute('SELECT status FROM summary_jobs WHERE reel_id=?', (original['id'],)).fetchone()[0] == 'done'
    assert len(models.get_all_reels()) == 2


def test_deletions_hidden_from_grid_counts_and_ready_but_history_survives(source):
    removed = next(r for r in models.get_all_reels() if r['provider_id'] == 'id:two')
    models.update_reel(removed['id'], {'notes': 'Keep history', 'final_post_text': 'Caption', 'status': 'ready', 'approved': True})
    source.pop()
    result = client.post('/api/reels/scan').json()
    assert result['missing_count'] == 1
    assert removed['id'] not in [r['id'] for r in client.get('/api/reels').json()]
    assert client.get('/api/reels?availability=missing').json()[0]['notes'] == 'Keep history'
    assert client.get('/api/reels/stats').json()['all'] == 1
    assert client.get('/api/reels?status=ready').json() == []
    assert models.get_ready_queue() == []
    history = next(r for r in client.get('/api/reels/library').json() if r['id'] == removed['id'])
    assert history['storage_status'] == 'missing'
    # Restoring the same provider file makes it visible again with all work intact.
    source.append(video('id:two', '/archive/SnapIGTik Download/restored.mp4'))
    archive.run_scan()
    assert models.get_reel_by_id(removed['id'])['notes'] == 'Keep history'
    assert removed['id'] in [r['id'] for r in client.get('/api/reels').json()]


def test_periodic_entry_point_repairs_stale_catalog_and_moved_parent_folder(source):
    before = {r['provider_id']: r['id'] for r in models.get_all_reels()}
    archive.set_state('dropbox_cursor', 'old-cursor-that-missed-an-event')
    source[:] = [video('id:one', '/archive/Renamed parent/nested/original.mp4')]
    result = archive.run_scan()
    assert result['moved'] == 1 and result['missing'] == 1
    assert models.get_reel_by_id(before['id:one'])['filename'] == 'original.mp4'
    assert models.get_reel_by_id(before['id:two'])['storage_status'] == 'missing'
    source.clear()  # Entire folder moved outside the configured archive/deleted.
    archive.run_scan()
    assert client.get('/api/reels').json() == []
    assert len(client.get('/api/reels?availability=missing').json()) == 2


def test_incomplete_provider_scan_preserves_paths_and_missing_state(source, monkeypatch):
    before = models.get_all_reels()
    def failed(cursor):
        raise StorageError('Second page unavailable')
    monkeypatch.setattr(dropbox, 'changes', failed)
    assert client.post('/api/reels/scan').status_code == 500
    assert models.get_all_reels() == before
    assert archive.get_state('dropbox_cursor') == 'fresh-cursor'


def test_rename_to_unsupported_extension_removes_from_video_view(source):
    source[0] = video('id:one', '/archive/SnapIGTik Download/original.txt')
    assert client.post('/api/reels/scan').json()['missing_count'] == 1
    assert all(r['provider_id'] != 'id:one' for r in client.get('/api/reels').json())
