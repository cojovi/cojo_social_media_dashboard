"""An agent can consume the real Ready workflow without owner mutation rights."""
from datetime import datetime
import pytest
from fastapi.testclient import TestClient

from app import models, jobs
from app.database import get_db_connection
from app.main import app
from app.settings import settings

client = TestClient(app)
agent = {'Authorization': 'Bearer ' + 'b' * 40}
owner = {'Authorization': 'Bearer ' + 'a' * 40}


@pytest.fixture
def catalog(clean_db, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, 'AUTH_REQUIRED', True)
    monkeypatch.setattr(settings, 'ADMIN_TOKEN', 'a' * 40)
    monkeypatch.setattr(settings, 'AGENT_TOKEN', 'b' * 40)
    def add(name='ready.mp4', **fields):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'test video bytes')
        reel_id = models.upsert_scanned_reel(dict(filename=path.name, filepath=str(path),
            file_extension='.mp4', file_size=16, duration_seconds=1, created_at='now'))
        values = dict(status='ready', approved=1, final_post_text='Approved caption',
                      hashtags='#approved', notes='Keep notes', source_version='rev1',
                      storage_status='local') | fields
        with get_db_connection() as conn:
            conn.execute(f"UPDATE reels SET {','.join(k+'=?' for k in values)} WHERE id=?", (*values.values(), reel_id))
            conn.commit()
        return reel_id
    return add


def claim(reel_id, key='request-one', platform='instagram', account='cmac-main'):
    response = client.post('/api/v1/publications', headers=agent,
        json=dict(reel_id=reel_id, platform=platform, account=account, idempotency_key=key))
    assert response.status_code == 201, response.text
    return response.json()


def ready_ids(params=None):
    response = client.get('/api/v1/queue/ready', headers=agent, params=params or {})
    assert response.status_code == 200, response.text
    return [r['id'] for r in response.json()['items']]


def test_ready_queue_is_agent_readable_strict_paginated_and_matches_dashboard(catalog):
    first = catalog()
    second = catalog('subfolder/second.mp4', storage_status='cloud')
    for i, fields in enumerate([{'status': 'draft'}, {'approved': 0},
                               {'final_post_text': ' \t\n\r'}, {'final_post_text': None},
                               {'storage_status': 'missing'}, {'status': 'archived'}, {'status': 'posted'}]):
        catalog(f'excluded-{i}.mp4', **fields)
    assert client.get('/api/v1/queue/ready').status_code == 401
    assert ready_ids() == [first, second]
    assert ready_ids() == sorted(r['id'] for r in models.get_ready_queue())
    dashboard = client.get('/api/reels?status=ready', headers=owner).json()
    assert sorted(r['id'] for r in dashboard) == ready_ids()
    assert [r['id'] for r in client.get('/api/v1/reels?status=ready', headers=agent).json()['items']] == ready_ids()
    page = client.get('/api/v1/queue/ready?limit=1', headers=agent).json()
    assert page['next_cursor'] == first
    assert ready_ids({'after_id': page['next_cursor'], 'limit': 1}) == [second]
    assert client.get('/api/v1/queue/ready', headers=agent, params={'after_id': second}).json() == {'items': [], 'next_cursor': None}
    for params in [{'platform': 'instagram'}, {'account': 'cmac-main'}, {'limit': 201}, {'after_id': -1}]:
        assert client.get('/api/v1/queue/ready', headers=agent, params=params).status_code == 422


def test_agent_claim_download_start_complete_moves_ready_to_posted(catalog):
    reel_id = catalog()
    assert ready_ids() == [reel_id]
    publication = claim(reel_id)
    base = '/api/v1/publications/' + publication['id']
    assert client.post(base+'/complete', headers=agent, json={'external_id': 'post-123'}).status_code == 409
    assert models.get_reel_by_id(reel_id)['status'] == 'ready'
    job = client.post(f'/api/v1/reels/{reel_id}/materialize', headers=agent).json()
    assert jobs.process_one(['materialize'])
    prepared = client.get('/api/v1/jobs/'+job['id'], headers=agent).json()
    assert prepared['status'] == 'succeeded'
    response = client.get(prepared['result']['download_url'], headers=agent,
                          params={'source_version': publication['source_version']})
    assert response.status_code == 200 and response.content == b'test video bytes'
    assert 'attachment' in response.headers['content-disposition']
    assert client.post(base+'/start', headers=agent).status_code == 200
    assert client.post(base+'/start', headers=agent).status_code == 409
    assert client.post(base+'/complete', headers=agent, json={'external_id': ' \t'}).status_code == 422
    # A fixture receipt simulates the external publisher's confirmed success.
    completed = client.post(base+'/complete', headers=agent, json={'external_id': 'post-123'})
    assert completed.status_code == 200
    receipt = completed.json()
    assert receipt['status'] == receipt['reel_status'] == 'posted'
    assert datetime.fromisoformat(receipt['reel_posted_at']).tzinfo is not None
    assert ready_ids() == [] and models.get_ready_queue() == []
    assert client.get('/api/reels?status=ready', headers=owner).json() == []
    posted = client.get('/api/reels?status=posted', headers=owner).json()
    assert [r['id'] for r in posted] == [reel_id]
    assert posted[0]['notes'] == 'Keep notes' and posted[0]['final_post_text'] == 'Approved caption'
    counts = client.get('/api/reels/stats', headers=owner).json()
    assert counts['ready'] == 0 and counts['posted'] == 1
    assert client.post(base+'/complete', headers=agent, json={'external_id': 'post-123'}).json() == receipt
    assert client.post(base+'/complete', headers=agent, json={'external_id': 'different-id'}).status_code == 409
    assert client.patch(f'/api/reels/{reel_id}', headers=agent, json={'status': 'ready'}).status_code == 403
    assert client.post(f'/api/reels/{reel_id}/mark-posted', headers=agent).status_code == 403


def test_target_filter_omits_active_uncertain_and_posted_but_not_expired_unstarted_claims(catalog):
    reel_id = catalog()
    target = {'platform': 'instagram', 'account': 'cmac-main'}
    publication = claim(reel_id)
    assert ready_ids() == [reel_id]  # Same eligibility as dashboard; target filtering is optional.
    assert ready_ids(target) == []
    assert ready_ids(target | {'account': 'different-account'}) == [reel_id]
    with get_db_connection() as conn:
        conn.execute('UPDATE publication_attempts SET lease_until=0 WHERE id=?', (publication['id'],))
        conn.commit()
    assert ready_ids(target) == [reel_id]
    for state in ['publishing', 'uncertain', 'posted']:
        with get_db_connection() as conn:
            conn.execute('UPDATE publication_attempts SET status=? WHERE id=?', (state, publication['id']))
            conn.commit()
        assert ready_ids(target) == []


@pytest.mark.parametrize('changes', [dict(final_post_text='New caption'), dict(hashtags='#new'),
                                    dict(source_version='rev2'), dict(status='draft'), dict(status='archived')])
def test_late_receipt_preserves_owner_changes_during_upload(catalog, changes):
    reel_id = catalog()
    publication = claim(reel_id)
    base = '/api/v1/publications/' + publication['id']
    assert client.post(base+'/start', headers=agent).status_code == 200
    with get_db_connection() as conn:
        conn.execute(f"UPDATE reels SET {','.join(k+'=?' for k in changes)} WHERE id=?", (*changes.values(), reel_id))
        conn.commit()
    receipt = client.post(base+'/complete', headers=agent, json={'external_id': 'confirmed-old-post'}).json()
    assert receipt['status'] == 'posted' and receipt['reel_status'] == changes.get('status', 'ready')
    current = models.get_reel_by_id(reel_id)
    assert current['posted_at'] is None
    assert all(current[k] == v for k, v in changes.items())


def test_completion_retry_never_consumes_a_subsequent_owner_edit(catalog):
    reel_id = catalog()
    publication = claim(reel_id)
    base = '/api/v1/publications/' + publication['id']
    client.post(base+'/start', headers=agent)
    client.post(base+'/complete', headers=agent, json={'external_id': 'post-123'})
    models.update_reel(reel_id, {'status': 'ready', 'final_post_text': 'New approved caption'})
    receipt = client.post(base+'/complete', headers=agent, json={'external_id': 'post-123'}).json()
    assert receipt['status'] == 'posted' and receipt['reel_status'] == 'ready'
    assert models.get_reel_by_id(reel_id)['final_post_text'] == 'New approved caption'


def test_expired_started_attempt_can_confirm_success_and_move_reel(catalog):
    reel_id = catalog()
    publication = claim(reel_id)
    base = '/api/v1/publications/' + publication['id']
    client.post(base+'/start', headers=agent)
    with get_db_connection() as conn:
        conn.execute('UPDATE publication_attempts SET lease_until=0 WHERE id=?', (publication['id'],))
        conn.commit()
    assert client.get(base, headers=agent).json()['status'] == 'uncertain'
    assert client.post(base+'/reconcile', headers=agent, json={'outcome': 'not_posted'}).status_code == 403
    receipt = client.post(base+'/complete', headers=agent, json={'external_id': 'verified-post-123'}).json()
    assert receipt['status'] == receipt['reel_status'] == 'posted'


def test_guide_and_openapi_are_available_to_agent_without_owner_access(catalog):
    response = client.get('/api/v1/guide', headers=agent)
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('text/markdown')
    assert '/queue/ready' in response.text and 'reel_status' in response.text
    assert 'private, no-store' in response.headers['cache-control']
    assert client.get('/api/v1/guide').status_code == 401
    schema = client.get('/openapi.json', headers=agent).json()
    assert '/api/v1/queue/ready' in schema['paths']
    assert '/api/v1/publications/{attempt_id}/complete' in schema['paths']
