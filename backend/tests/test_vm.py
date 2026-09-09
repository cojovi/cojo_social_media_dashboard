import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
import pytest
import httpx
from fastapi.testclient import TestClient
from app.main import app
from app.settings import settings
from app.database import get_db_connection, init_db
from app.dropbox_storage import dropbox, sync_dropbox, StorageError
from app import models, jobs
from app.media_cache import MediaCache, DropboxHash

client = TestClient(app)


@pytest.fixture
def vm_db(clean_db):
    with get_db_connection() as conn:
        conn.execute('DELETE FROM transfer_jobs')
        conn.execute('DELETE FROM publication_attempts')
        conn.execute('DELETE FROM cache_entries')
        conn.commit()


@pytest.fixture
def media(tmp_path, monkeypatch, vm_db):
    monkeypatch.setattr(settings, 'CACHE_FOLDER', tmp_path / 'cache')
    monkeypatch.setattr(settings, 'CACHE_MAX_BYTES', 100)
    monkeypatch.setattr(settings, 'MIN_FREE_DISK_BYTES', 0)
    monkeypatch.setattr(settings, 'CACHE_TTL_SECONDS', 43200)
    instance = MediaCache()
    instance.start()
    yield instance
    instance.owner.close()


def reel(key='one', size=10):
    return {'provider_id': 'id:' + key, 'source_version': 'rev1', 'file_size': size,
            'storage_status': 'cloud', 'content_hash': None}


def fake_download(reel, write):
    write(b'x' * reel['file_size'])


def test_cache_deduplicates_and_pins(media, monkeypatch):
    calls = []
    monkeypatch.setattr(dropbox, 'download', lambda reel, write: (calls.append(1), fake_download(reel, write)))
    path, key = media.acquire(reel(size=60))
    path2, key2 = media.acquire(reel(size=60))
    assert path == path2 and len(calls) == 1
    with pytest.raises(StorageError, match='active files'):
        media.acquire(reel('two', 50))
    media.release(key)
    with pytest.raises(StorageError):
        media.acquire(reel('two', 50))
    media.release(key2)
    other, other_key = media.acquire(reel('two', 50))
    assert other.exists() and not path.exists()
    media.release(other_key)


def test_five_concurrent_transfers_share_reservations(media, monkeypatch):
    entered = threading.Event()
    unblock = threading.Event()
    lock = threading.Lock()
    active = 0
    maximum = 0
    def transfer(item, write):
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(active, maximum)
            if active == 5:
                entered.set()
        assert unblock.wait(5)
        fake_download(item, write)
        with lock:
            active -= 1
    monkeypatch.setattr(dropbox, 'download', transfer)
    def run(i):
        path, key = media.acquire(reel(str(i)))
        assert path.stat().st_size == 10
        media.release(key)
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(run, i) for i in range(8)]
        try:
            assert entered.wait(5)
            assert media.status()['active_downloads'] == 5
            assert media.status()['entries'] == [{'state': 'downloading', 'files': 5, 'bytes': 50}]
        finally:
            unblock.set()
        for future in futures:
            future.result(5)
    assert maximum == 5
    assert not list(settings.CACHE_FOLDER.glob('*.part'))


def test_integrity_failures_remove_partial_and_reservation(media, monkeypatch):
    for payload in (b'x' * 9, b'x' * 11):
        monkeypatch.setattr(dropbox, 'download', lambda item, write: write(payload))
        with pytest.raises(StorageError):
            media.acquire(reel())
        assert not media.reserved
        assert not list(settings.CACHE_FOLDER.glob('*.part'))
        assert media.status()['entries'] == []
    monkeypatch.setattr(dropbox, 'download', fake_download)
    item = reel()
    item['content_hash'] = 'incorrect'
    with pytest.raises(StorageError, match='integrity'):
        media.acquire(item)


def test_disk_reserve_includes_other_unwritten_transfers(media, monkeypatch):
    monkeypatch.setattr(settings, 'MIN_FREE_DISK_BYTES', 50)
    monkeypatch.setattr('app.media_cache.shutil.disk_usage', lambda path: SimpleNamespace(free=70))
    media.reserved['other-transfer'] = 15
    monkeypatch.setattr(dropbox, 'download', fake_download)
    with pytest.raises(StorageError, match='reserve'):
        media.acquire(reel(size=10))


def test_original_download_preserves_preview_encoder_reservation(media, monkeypatch):
    media.auxiliary_reserved = 25
    monkeypatch.setattr('app.media_cache.shutil.disk_usage', lambda path: SimpleNamespace(free=30))
    monkeypatch.setattr(dropbox, 'download', lambda *args: pytest.fail('Must reserve before download'))
    with pytest.raises(StorageError, match='reserve'):
        media.acquire(reel(size=10))


def test_expiration_and_restart_cleanup(media, monkeypatch):
    monkeypatch.setattr(dropbox, 'download', fake_download)
    path, key = media.acquire(reel())
    monkeypatch.setattr(settings, 'CACHE_TTL_SECONDS', 0)
    media.cleanup()
    assert path.exists()  # TTL never removes a reader's file.
    media.release(key)
    media.cleanup()
    assert not path.exists()
    abandoned = settings.CACHE_FOLDER / ('a' * 64 + '.part')
    abandoned.write_bytes(b'partial')
    with get_db_connection() as conn:
        conn.execute("INSERT INTO cache_entries VALUES ('abandoned', 99, 'downloading', 0)")
        conn.commit()
    media.owner.close()
    media.owner = None
    media.start()
    assert not abandoned.exists() and media.status()['entries'] == []


def test_single_process_owner(media):
    with pytest.raises(RuntimeError, match='one Uvicorn worker'):
        MediaCache().start()


def test_dropbox_block_hash():
    data = b'1234' * (1024 * 1024 + 17)
    expected = hashlib.sha256(b''.join(hashlib.sha256(data[i:i+4194304]).digest() for i in range(0, len(data), 4194304))).hexdigest()
    hasher = DropboxHash()
    for i in range(0, len(data), 77777):
        hasher.update(data[i:i+77777])
    assert hasher.hexdigest() == expected


def entry(file_id='id:one', path='/archive/a.mp4', rev='abc'):
    return {'.tag': 'file', 'id': file_id, 'name': Path(path).name, 'path_lower': path,
            'path_display': path, 'rev': rev, 'size': 10, 'server_modified': '2026-09-05T00:00:00Z', 'content_hash': None}


def test_dropbox_identity_move_revision_and_replacement(vm_db, monkeypatch):
    def sync(entries, full=False):
        monkeypatch.setattr(dropbox, 'changes', lambda cursor: (entries, 'cursor1', full))
        return sync_dropbox()
    assert sync([entry()], True)['added'] == 1
    original = models.get_all_reels()[0]
    models.update_reel(original['id'], {'final_post_text': 'Approved caption', 'notes': 'Keep these notes', 'status': 'ready', 'approved': True})
    sync([entry(path='/archive/moved.mp4')])
    moved = models.get_reel_by_id(original['id'])
    assert moved['approved'] and moved['notes'] == 'Keep these notes'
    sync([entry(path='/archive/moved.mp4', rev='new')])
    updated = models.get_reel_by_id(original['id'])
    assert not updated['approved'] and updated['status'] == 'needs_review'
    assert updated['final_post_text'] == 'Approved caption'
    sync([{'.tag': 'deleted', 'path_lower': '/archive/moved.mp4'}, entry('id:replacement', '/archive/moved.mp4')])
    assert len(models.get_all_reels()) == 2
    assert models.get_reel_by_id(original['id'])['storage_status'] == 'missing'


def test_failed_sync_never_advances_cursor_or_marks_missing(vm_db, monkeypatch):
    monkeypatch.setattr(dropbox, 'changes', lambda cursor: ([entry()], 'cursor1', True))
    sync_dropbox()
    def failed(cursor):
        raise StorageError('page two failed')
    monkeypatch.setattr(dropbox, 'changes', failed)
    with pytest.raises(StorageError):
        sync_dropbox()
    assert models.get_all_reels()[0]['storage_status'] == 'cloud'
    from app.archive import get_state
    assert get_state('dropbox_cursor', None) == 'cursor1'


def test_oauth_uses_pkce_offline_and_readonly(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'DROPBOX_CREDENTIALS_PATH', tmp_path / 'secrets/dropbox.json')
    result = dropbox.begin('testappkey123', '/archive')
    assert 'code_challenge_method=S256' in result['authorize_url']
    assert 'token_access_type=offline' in result['authorize_url']
    assert 'write' not in result['authorize_url'] and 'secret' not in result['authorize_url']
    with pytest.raises(StorageError, match='expired'):
        dropbox.finish('incorrect-flow', 'code')


def test_dropbox_http_contract_and_pkce_completion(tmp_path, monkeypatch):
    from app.dropbox_storage import Dropbox
    provider = Dropbox()
    credential_file = tmp_path / 'secrets/dropbox.json'
    monkeypatch.setattr(settings, 'DROPBOX_CREDENTIALS_PATH', credential_file)
    requests = []
    def handler(request):
        requests.append(request)
        if request.url.path == '/oauth2/token':
            return httpx.Response(200, json={'access_token': 'test-access', 'refresh_token': 'test-refresh', 'expires_in': 14400})
        if request.url.path.endswith('/users/get_current_account'):
            return httpx.Response(200, json={'root_info': {'root_namespace_id': '12345'}})
        assert request.headers['authorization'] == 'Bearer test-access'
        assert json.loads(request.headers['Dropbox-API-Path-Root']) == {'.tag': 'root', 'root': '12345'}
        if request.url.path.endswith('/files/download'):
            # The real API rejects a separate `rev` field with HTTP 400.
            assert json.loads(request.headers['Dropbox-API-Arg']) == {'path': 'rev:rev1'}
            return httpx.Response(200, content=b'0123456789', headers={'Dropbox-API-Result': json.dumps({'id': 'id:one', 'rev': 'rev1'})})
        assert request.url.path.endswith('/files/list_folder')
        assert json.loads(request.content)['recursive'] is True
        return httpx.Response(200, json={'entries': [entry()], 'has_more': False, 'cursor': 'next'})
    real_client = httpx.Client
    monkeypatch.setattr('app.dropbox_storage.httpx.Client', lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    flow = provider.begin('testapp123', '/archive')
    connected = provider.finish(flow['flow_id'], 'one-time-code')
    assert connected == {'connected': True, 'folder': '/archive'}
    assert credential_file.stat().st_mode & 0o777 == 0o600
    assert b'code_verifier=' in requests[0].content and b'client_secret' not in requests[0].content
    entries, cursor, full = provider.changes()
    assert len(entries) == 1 and cursor == 'next' and full
    chunks = []
    provider.download(reel(), chunks.append)
    assert b''.join(chunks) == b'0123456789'


@pytest.mark.parametrize('metadata', [{'id': 'id:other', 'rev': 'rev1'}, {'id': 'id:one', 'rev': 'other'}])
def test_revision_download_rejects_wrong_identity_before_serving_bytes(monkeypatch, metadata):
    from app.dropbox_storage import Dropbox
    provider = Dropbox()
    monkeypatch.setattr(provider, 'headers', lambda: {'Authorization': 'Bearer test-token'})
    def handler(request):
        assert json.loads(request.headers['Dropbox-API-Arg']) == {'path': 'rev:rev1'}
        return httpx.Response(200, content=b'wrong-file', headers={'Dropbox-API-Result': json.dumps(metadata)})
    real_client = httpx.Client
    monkeypatch.setattr('app.dropbox_storage.httpx.Client', lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    chunks = []
    with pytest.raises(StorageError, match='different file revision'):
        provider.download(reel(), chunks.append)
    assert chunks == []


def test_hosted_auth_and_agent_scope(monkeypatch, vm_db):
    monkeypatch.setattr(settings, 'AUTH_REQUIRED', True)
    monkeypatch.setattr(settings, 'ADMIN_TOKEN', 'a' * 40)
    monkeypatch.setattr(settings, 'AGENT_TOKEN', 'b' * 40)
    monkeypatch.setattr(settings, 'COOKIE_SECURE', False)
    browser = TestClient(app)
    for path in ['/api/reels', '/api/v1/storage', '/thumbnails/private.jpg', '/openapi.json']:
        assert browser.get(path).status_code == 401
    assert browser.get('/healthz').status_code == 200
    agent = {'Authorization': 'Bearer ' + 'b' * 40}
    assert browser.get('/api/v1/reels', headers=agent).status_code == 200
    assert browser.post('/api/reels/1/mark-ready', headers=agent).status_code == 403
    assert browser.post('/api/v1/storage/refresh', headers=agent).status_code == 403
    assert browser.post('/api/auth/login', json={'token': 'a' * 40}, headers={'Origin': 'https://evil.test'}).status_code == 403
    response = browser.post('/api/auth/login', json={'token': 'a' * 40})
    assert response.status_code == 200 and 'HttpOnly' in response.headers['set-cookie']
    assert browser.get('/api/reels').status_code == 200
    assert browser.post('/api/auth/logout').status_code == 200
    assert browser.get('/api/reels').status_code == 401


@pytest.mark.parametrize('origin', [
    'http://127.0.0.1:18765', 'http://localhost:18765', 'http://[::1]:18765',
])
def test_loopback_login_and_logout_allow_equivalent_names(monkeypatch, origin):
    monkeypatch.setattr(settings, 'AUTH_REQUIRED', True)
    monkeypatch.setattr(settings, 'PUBLIC_ORIGIN', 'http://127.0.0.1:18765')
    monkeypatch.setattr(settings, 'ADMIN_TOKEN', 'a' * 40)
    monkeypatch.setattr(settings, 'COOKIE_SECURE', False)
    # Exercise the Origin header independently of the test transport's IPv6 support.
    browser = TestClient(app, base_url='http://127.0.0.1:18765')
    response = browser.post('/api/auth/login', json={'token': 'a' * 40}, headers={'Origin': origin})
    assert response.status_code == 200
    assert browser.get('/api/auth/session').json()['authenticated']
    assert browser.post('/api/auth/logout', headers={'Origin': origin}).status_code == 200
    assert not browser.get('/api/auth/session').json()['authenticated']


@pytest.mark.parametrize('origin', [
    'null', 'https://evil.test', 'http://localhost:18766', 'http://127.0.0.1',
    'https://localhost:18765', 'http://localhost.evil.test:18765',
    'http://127.0.0.2:18765', 'http://localhost:18765@evil.test',
])
def test_loopback_origin_guard_rejects_other_sites_ports_and_schemes(monkeypatch, origin):
    monkeypatch.setattr(settings, 'AUTH_REQUIRED', True)
    monkeypatch.setattr(settings, 'PUBLIC_ORIGIN', 'http://127.0.0.1:18765')
    monkeypatch.setattr(settings, 'ADMIN_TOKEN', 'a' * 40)
    browser = TestClient(app)
    # Host headers cannot expand the allowlist (including behind a future proxy).
    headers = {'Origin': origin, 'Host': 'evil.test', 'X-Forwarded-Host': 'evil.test'}
    assert browser.post('/api/auth/login', json={'token': 'a' * 40}, headers=headers).status_code == 403


def test_public_origin_does_not_trust_loopback_aliases(monkeypatch):
    monkeypatch.setattr(settings, 'AUTH_REQUIRED', True)
    monkeypatch.setattr(settings, 'PUBLIC_ORIGIN', 'https://reels.example.test')
    monkeypatch.setattr(settings, 'ADMIN_TOKEN', 'a' * 40)
    assert settings.allowed_browser_origins == {'https://reels.example.test'}
    browser = TestClient(app)
    for origin in ['http://localhost:18765', 'https://localhost', 'https://evil.test']:
        assert browser.post('/api/auth/login', json={'token': 'a' * 40}, headers={'Origin': origin}).status_code == 403
    assert browser.post('/api/auth/login', json={'token': 'a' * 40},
                        headers={'Origin': 'https://reels.example.test'}).status_code == 200


def approved_reel():
    key = models.upsert_scanned_reel({'filename': 'approved.mp4', 'filepath': '/archive/approved.mp4',
        'file_extension': '.mp4', 'file_size': 10, 'duration_seconds': 1, 'created_at': 'now'})
    models.update_reel(key, {'final_post_text': 'Human-approved caption', 'approved': True, 'status': 'ready'})
    return key


def test_publication_idempotency_target_lock_and_uncertainty(vm_db):
    reel_id = approved_reel()
    body = {'reel_id': reel_id, 'platform': 'instagram', 'account': 'cmac', 'idempotency_key': 'request-one'}
    response = client.post('/api/v1/publications', json=body)
    assert response.status_code == 201, response.text
    attempt = response.json()
    assert client.post('/api/v1/publications', json=body).json()['id'] == attempt['id']
    assert client.post('/api/v1/publications', json={**body, 'idempotency_key': 'request-two'}).status_code == 409
    url = f"/api/v1/publications/{attempt['id']}"
    assert client.post(url + '/start').status_code == 200
    assert client.post(url + '/start').status_code == 409
    with get_db_connection() as conn:
        conn.execute('UPDATE publication_attempts SET lease_until=0')
        conn.commit()
    assert client.get(url).json()['status'] == 'uncertain'
    assert client.post(url + '/release').status_code == 409
    assert client.post(url + '/complete', json={'external_id': 'ig-123'}).json()['status'] == 'posted'
    assert client.post(url + '/complete', json={'external_id': 'ig-123'}).status_code == 200
    assert client.post(url + '/complete', json={'external_id': 'ig-other'}).status_code == 409
    assert client.post('/api/v1/publications', json={**body, 'platform': 'tiktok', 'idempotency_key': 'request-three'}).status_code == 201


def test_publication_snapshot_changes_require_review(vm_db):
    reel_id = approved_reel()
    attempt = client.post('/api/v1/publications', json={'reel_id': reel_id, 'platform': 'instagram', 'account': 'cmac', 'idempotency_key': 'request-four'}).json()
    models.update_reel(reel_id, {'final_post_text': 'Changed after claim'})
    assert client.post(f"/api/v1/publications/{attempt['id']}/start").status_code == 409


def test_durable_jobs_deduplicate_and_fail_stale_revision(vm_db):
    reel_id = approved_reel()
    first = jobs.enqueue('materialize', reel_id)
    assert jobs.enqueue('materialize', reel_id)['id'] == first['id']
    with get_db_connection() as conn:
        conn.execute("UPDATE reels SET source_version='new' WHERE id=?", (reel_id,))
        conn.commit()
    assert jobs.process_one(['materialize'])
    response = client.get('/api/v1/jobs/' + first['id']).json()
    assert response['status'] == 'failed' and 'revision changed' in response['error']


def test_keyset_pagination(vm_db):
    approved_reel()
    models.upsert_scanned_reel({'filename': 'second.mp4', 'filepath': '/archive/second.mp4', 'file_extension': '.mp4',
                              'file_size': 10, 'duration_seconds': 1, 'created_at': 'now'})
    first = client.get('/api/v1/reels?limit=1').json()
    second = client.get('/api/v1/reels', params={'limit': 1, 'after_id': first['next_cursor']}).json()
    assert first['items'][0]['id'] != second['items'][0]['id']
    assert second['next_cursor'] is None


def test_cached_range_download_releases_reader_pin(media, monkeypatch):
    monkeypatch.setattr(dropbox, 'changes', lambda cursor: ([entry()], 'cursor1', True))
    sync_dropbox()
    monkeypatch.setattr(dropbox, 'download', fake_download)
    monkeypatch.setattr('app.routes.reels.cache', media)
    reel_id = models.get_all_reels()[0]['id']
    response = client.get(f'/api/v1/reels/{reel_id}/download', headers={'Range': 'bytes=2-4'})
    assert response.status_code == 206 and response.content == b'xxx'
    assert 'attachment' in response.headers['content-disposition']
    assert media.status()['pinned_files'] == 0
    assert client.get(f'/api/v1/reels/{reel_id}/download?source_version=wrong').status_code == 409
