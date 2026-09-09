"""Preview storage and queue invariants, plus real ffmpeg codec/playback artifacts."""
import json
import shutil
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from app import models
from app.archive import set_state
from app.database import get_db_connection
from app.dropbox_storage import StorageError
from app.main import app
from app.media_cache import cache
from app.previews import PreviewStore, preview_key, encode_preview, MAX_CLIP_BYTES, SCRATCH_BYTES
from app.settings import settings


@pytest.fixture
def store(clean_db, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, 'PREVIEWS_FOLDER', tmp_path / 'previews')
    monkeypatch.setattr(settings, 'PREVIEW_MAX_BYTES', 1_000_000_000)
    monkeypatch.setattr(settings, 'AUTO_PREVIEWS', True)
    monkeypatch.setattr(settings, 'MIN_FREE_DISK_BYTES', 0)
    with get_db_connection() as conn:
        conn.execute('DELETE FROM cache_entries')
        conn.commit()
    instance = PreviewStore()
    instance.initialize()
    monkeypatch.setattr('app.routes.v1.previews', instance)
    yield instance
    assert instance.reserved == 0 and cache.auxiliary_reserved == 0


def add(tmp_path, name='one.mp4', **fields):
    path = tmp_path / name
    path.write_bytes(b'source video')
    info = path.stat()
    reel_id = models.upsert_scanned_reel(dict(filename=name, filepath=str(path),
        file_extension='.mp4', file_size=info.st_size, duration_seconds=30, created_at='now'))
    values = dict(storage_status='local', source_version=f'{info.st_size}:{info.st_mtime_ns}',
                  status='ready', approved=1, final_post_text='Keep this caption', notes='Keep notes') | fields
    with get_db_connection() as conn:
        conn.execute(f"UPDATE reels SET {','.join(k+'=?' for k in values)} WHERE id=?", (*values.values(), reel_id))
        conn.commit()
    return models.get_reel_by_id(reel_id)


def fake_encode(source, directory):
    output = directory / 'preview.mp4'
    output.write_bytes(b'small preview')
    return output, 9


def row(key):
    with get_db_connection() as conn:
        result = conn.execute('SELECT * FROM preview_assets WHERE key=?', (key,)).fetchone()
    return dict(result) if result else None


def change(reel, **fields):
    with get_db_connection() as conn:
        conn.execute(f"UPDATE reels SET {','.join(k+'=?' for k in fields)} WHERE id=?", (*fields.values(), reel['id']))
        conn.commit()
    return models.get_reel_by_id(reel['id'])


def test_identity_deduplicates_only_verified_exact_copies(tmp_path, store):
    first = add(tmp_path, storage_provider='dropbox', content_hash='a' * 64)
    copy = add(tmp_path, 'copy.mp4', storage_provider='dropbox', content_hash='a' * 64, source_version='different')
    assert preview_key(first) == preview_key(copy)
    assert preview_key(first) != preview_key(dict(copy, file_size=99))
    assert preview_key(first) != preview_key(dict(copy, content_hash='b' * 64))
    assert preview_key(dict(first, content_hash=None)) != preview_key(dict(copy, content_hash=None))
    store.reconcile()
    assert store.status()['jobs'] == {'queued': 1}


def test_get_is_metadata_only_and_generation_keeps_editorial_fields(store, tmp_path, monkeypatch):
    reel = add(tmp_path)
    calls = []
    monkeypatch.setattr('app.previews.encode_preview', lambda *args: (calls.append(1), fake_encode(*args))[1])
    client = TestClient(app)
    endpoint = f"/api/v1/reels/{reel['id']}/preview"
    assert client.get(endpoint).json()['status'] == 'not_generated'
    assert calls == [] and store.status()['jobs'] == {}
    assert client.post(endpoint).status_code == 202
    assert client.post(endpoint).status_code == 202  # Deduplicate repeated clicks.
    assert store.process_one()
    assert len(calls) == 1
    info = client.get(endpoint).json()
    assert info['status'] == 'ready' and info['duration_seconds'] == 9
    assert models.get_reel_by_id(reel['id']) == reel
    response = client.get(info['url'], headers={'Range': 'bytes=0-4'})
    assert response.status_code == 206 and response.content == b'small'
    assert response.headers['cache-control'] == 'private, no-store'
    assert store.pins[info['key']] == 0


def test_agent_can_read_but_not_request_or_pause(store, tmp_path, monkeypatch):
    reel = add(tmp_path)
    monkeypatch.setattr(settings, 'AUTH_REQUIRED', True)
    monkeypatch.setattr(settings, 'ADMIN_TOKEN', 'a' * 40)
    monkeypatch.setattr(settings, 'AGENT_TOKEN', 'b' * 40)
    client = TestClient(app)
    path = f"/api/v1/reels/{reel['id']}/preview"
    headers = {'Authorization': 'Bearer ' + 'b' * 40}
    assert client.get(path).status_code == 401
    assert client.get(path, headers=headers).status_code == 200
    assert client.post(path, headers=headers).status_code == 403
    assert client.post('/api/v1/previews/pause', json={'paused': True}, headers=headers).status_code == 403
    owner = {'Authorization': 'Bearer ' + 'a' * 40}
    assert client.post('/api/v1/previews/pause', json={'paused': True}, headers=owner).json()['paused'] is True


def test_source_rename_reuses_preview_and_revision_invalidates(store, tmp_path, monkeypatch):
    reel = add(tmp_path, storage_provider='dropbox', content_hash='a' * 64)
    key = store.enqueue(reel)['key']
    store.path(key).write_bytes(b'preview')
    with get_db_connection() as conn:
        conn.execute("UPDATE preview_assets SET status='ready',size=7 WHERE key=?", (key,))
        conn.commit()
    renamed = change(reel, filename='renamed.mp4', provider_path='/other/renamed.mp4')
    assert store.info(renamed)['status'] == 'ready'
    updated = change(reel, source_version='rev2', content_hash='b' * 64)
    assert store.info(updated)['status'] == 'not_generated'
    with pytest.raises(StorageError, match='older revision'):
        store.acquire(updated, key)
    store.reconcile()
    assert not store.path(key).exists() and row(key) is None
    missing = change(updated, storage_status='missing')
    assert store.info(missing)['status'] == 'unavailable'
    store.reconcile()
    assert store.status()['jobs'] == {}


def test_revision_change_during_encode_discards_output(store, tmp_path, monkeypatch):
    reel = add(tmp_path)
    key = store.enqueue(reel)['key']
    def encode(*args):
        change(reel, source_version='new revision')
        return fake_encode(*args)
    monkeypatch.setattr('app.previews.encode_preview', encode)
    store.process_one()
    assert row(key)['status'] == 'failed'
    assert not list(settings.PREVIEWS_FOLDER.glob('*.mp4'))
    assert not list(settings.PREVIEWS_FOLDER.glob('work-*'))


def test_budget_waits_without_fetching_or_churning_and_pins_protect_eviction(store, tmp_path, monkeypatch):
    old = add(tmp_path)
    key = store.enqueue(old)['key']
    store.path(key).write_bytes(b'1234567890')
    with get_db_connection() as conn:
        conn.execute("UPDATE preview_assets SET status='ready',size=10 WHERE key=?", (key,))
        conn.commit()
    monkeypatch.setattr(settings, 'PREVIEW_MAX_BYTES', SCRATCH_BYTES)
    newer = add(tmp_path, 'new.mp4')
    store.enqueue(newer)
    monkeypatch.setattr('app.previews.local_media', lambda *args: pytest.fail('Capacity must be checked before downloading'))
    store.process_one()
    assert store.info(newer)['status'] == 'queued' and store.path(key).exists()
    assert store.status()['blocked_reason']
    _, pinned = store.acquire(old, key)
    with pytest.raises(StorageError):
        store.reserve(requested=True)
    assert store.path(key).exists()
    store.release(pinned)
    store.reserve(requested=True)
    assert not store.path(key).exists() and row(key)['status'] == 'evicted'
    # Release the test's direct reservation; the worker normally handles this in finally.
    store.reserved = cache.auxiliary_reserved = 0
    store.reconcile()
    assert row(key)['status'] == 'evicted'


def test_pause_stops_backfill_but_request_has_priority(store, tmp_path, monkeypatch):
    older = add(tmp_path)
    newer = add(tmp_path, 'new.mp4')
    store.reconcile()
    set_state('previews_paused', True)
    assert store.process_one() is False
    store.enqueue(older, requested=True)
    monkeypatch.setattr('app.previews.encode_preview', fake_encode)
    assert store.process_one()
    assert store.info(older)['status'] == 'ready' and store.info(newer)['status'] == 'queued'


def test_local_placeholders_are_not_hydrated_by_backfill(store, tmp_path, monkeypatch):
    reel = add(tmp_path, storage_status='cloud')
    monkeypatch.setattr('app.previews.storage_status', lambda path: 'cloud')
    monkeypatch.setattr('app.previews.local_media', lambda *args: pytest.fail('Automatic local hydration'))
    store.reconcile()
    assert store.status()['jobs'] == {}
    store.enqueue(reel)  # Even an older queued job must recheck local availability.
    assert store.process_one() is False


def test_cached_originals_are_prioritized_and_reused(store, tmp_path, monkeypatch):
    older = add(tmp_path, storage_provider='dropbox', provider_id='id:one')
    newer = add(tmp_path, 'new.mp4', storage_provider='dropbox', provider_id='id:two')
    from app.media_cache import cache_key
    with get_db_connection() as conn:
        conn.execute("INSERT INTO cache_entries VALUES (?,12,'ready',?)", (cache_key(older), time.time()))
        conn.commit()
    selected = []
    @contextmanager
    def media(reel):
        selected.append(reel['id'])
        yield Path(reel['filepath'])
    monkeypatch.setattr('app.previews.local_media', media)
    monkeypatch.setattr('app.previews.encode_preview', fake_encode)
    store.reconcile()
    store.process_one()
    assert selected == [older['id']]
    assert store.info(newer)['status'] == 'queued'


def test_failed_encoder_cleans_scratch_and_can_be_retried(store, tmp_path, monkeypatch):
    reel = add(tmp_path)
    key = store.enqueue(reel)['key']
    def broken(source, directory):
        (directory / 'partial.mp4').write_bytes(b'partial')
        raise subprocess.TimeoutExpired('ffmpeg', 45)
    monkeypatch.setattr('app.previews.encode_preview', broken)
    store.process_one()
    assert row(key)['status'] == 'failed'
    assert not list(settings.PREVIEWS_FOLDER.glob('work-*'))
    monkeypatch.setattr('app.previews.encode_preview', fake_encode)
    store.enqueue(reel, requested=True)
    store.process_one()
    assert store.info(reel)['status'] == 'ready'


def test_restart_recovers_work_and_missing_files_without_redownload_loop(store, tmp_path):
    reel = add(tmp_path)
    key = store.enqueue(reel)['key']
    with get_db_connection() as conn:
        conn.execute("UPDATE preview_assets SET status='running' WHERE key=?", (key,))
        conn.commit()
    scratch = settings.PREVIEWS_FOLDER / 'work-abandoned'
    scratch.mkdir()
    (scratch / 'partial.mp4').write_bytes(b'partial')
    restarted = PreviewStore()
    restarted.initialize()
    assert row(key)['status'] == 'queued' and not scratch.exists()
    with get_db_connection() as conn:
        conn.execute("UPDATE preview_assets SET status='ready',size=40 WHERE key=?", (key,))
        conn.commit()
    restarted.initialize()
    assert row(key)['status'] == 'evicted'
    restarted.enqueue(reel, requested=True)
    assert row(key)['status'] == 'queued'


@pytest.mark.parametrize('duration', [2, 18])
def test_real_ffmpeg_produces_small_silent_h264_samples(tmp_path, duration):
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        pytest.skip('ffmpeg not installed')
    source = tmp_path / 'source.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=size=720x1280:rate=15',
                    '-f', 'lavfi', '-i', 'sine=frequency=440', '-t', str(duration), '-c:v', 'libx264',
                    '-preset', 'ultrafast', '-threads', '1', '-c:a', 'aac', str(source)], check=True, timeout=45)
    work = tmp_path / 'work'
    work.mkdir()
    output, actual_duration = encode_preview(source, work)
    info = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(output)]))
    assert len(info['streams']) == 1
    stream = info['streams'][0]
    assert stream['codec_name'] == 'h264' and stream['pix_fmt'] == 'yuv420p'
    assert max(stream['width'], stream['height']) <= 360
    assert abs(actual_duration - min(duration, 9)) < .5
    assert 0 < output.stat().st_size <= MAX_CLIP_BYTES
    assert sum(p.stat().st_size for p in work.iterdir()) < SCRATCH_BYTES
