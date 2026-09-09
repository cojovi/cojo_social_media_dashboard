import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import get_db_connection
from app.settings import settings

client = TestClient(app)


@pytest.fixture
def catalog(clean_db):
    with get_db_connection() as conn:
        for name, folder, status in [('one.mp4', 'SnapIGTik Download', 'draft'),
                                     ('copy.mp4', 'SnapIGTik Download/artistic', 'posted')]:
            conn.execute("""INSERT INTO reels(filename,filepath,file_extension,file_size,duration_seconds,
                created_at,updated_at,discovered_at,storage_provider,content_hash,status,notes)
                VALUES (?,?,'.mp4',10,2,'now','now','now','dropbox',?,?,?)""",
                (name, f'dropbox:/archive/{folder}/{name}', 'a' * 64, status, 'Preserve private notes'))
        conn.commit()
        return [dict(row) for row in conn.execute('SELECT * FROM reels ORDER BY id')]


def test_library_is_lightweight_unfiltered_and_read_only(catalog):
    response = client.get('/api/reels/library?status=draft&search=does-not-exist')
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 2
    assert set(rows[0]) == {'id', 'filename', 'filepath', 'file_size', 'storage_provider', 'content_hash', 'status', 'storage_status'}
    assert rows[0]['content_hash'] == rows[1]['content_hash'] == 'a' * 64
    assert rows[0]['id'] != rows[1]['id']
    with get_db_connection() as conn:
        assert [dict(row) for row in conn.execute('SELECT * FROM reels ORDER BY id')] == catalog


def test_grid_and_detail_expose_copy_identity_without_losing_filters(catalog):
    rows = client.get('/api/reels?status=draft').json()
    assert len(rows) == 1 and rows[0]['content_hash'] == 'a' * 64
    assert rows[0]['notes'] == 'Preserve private notes'
    assert client.get(f"/api/reels/{catalog[1]['id']}").json()['content_hash'] == 'a' * 64


def test_library_remains_owner_only(catalog, monkeypatch):
    monkeypatch.setattr(settings, 'AUTH_REQUIRED', True)
    monkeypatch.setattr(settings, 'ADMIN_TOKEN', 'owner-library-test')
    monkeypatch.setattr(settings, 'AGENT_TOKEN', 'agent-library-test')
    assert client.get('/api/reels/library').status_code == 401
    assert client.get('/api/reels/library', headers={'Authorization': 'Bearer agent-library-test'}).status_code == 403
    response = client.get('/api/reels/library', headers={'Authorization': 'Bearer owner-library-test'})
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'private, no-store'
