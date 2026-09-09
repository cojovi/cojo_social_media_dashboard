import hashlib
import json
import sqlite3
from pathlib import Path
import pytest
from app.catalog_import import import_catalog
from app.database import get_db_connection
from app.settings import settings


@pytest.fixture
def bundle(clean_db, tmp_path):
    with get_db_connection() as conn:
        conn.execute("""INSERT INTO reels(filename,filepath,file_extension,file_size,duration_seconds,
            created_at,updated_at,discovered_at,storage_provider,provider_id,provider_path,source_version,
            content_hash,notes,final_post_text,approved,status)
            VALUES ('a.mp4','dropbox:a','.mp4',10,2,'now','now','now','dropbox','id:a','/archive/a.mp4',
                    'rev1','hash1','Keep notes','Keep caption',1,'ready')""")
        reel_id = conn.execute("SELECT id FROM reels WHERE provider_id='id:a'").fetchone()[0]
        conn.execute("INSERT INTO summary_jobs(reel_id,updated_at) VALUES (?,'now')", (reel_id,))
        conn.commit()
    thumb_dir = tmp_path / 'bundle' / 'thumbnails'
    thumb_dir.mkdir(parents=True)
    data = b'known-thumbnail'
    digest = hashlib.sha256(data).hexdigest()
    filename = f'mac-import-{digest}.jpg'
    (thumb_dir / filename).write_bytes(data)
    manifest = {'version':1, 'source_database':'mac.db', 'entries':[{
        'target':{'id':reel_id,'provider_id':'id:a','provider_path':'/archive/a.mp4',
                  'source_version':'rev1','file_size':10,'content_hash':'hash1'},
        'source':{'id':999,'quick_summary':'Original description','quick_summary_model':'gemini-2.5-flash-lite',
                  'quick_summary_at':'original-date','notes':'Must not import','approved':False},
        'match':{'method':'path_size_mtime','file_size':10,'mtime_delta_ns':0},
        'thumbnail':{'filename':filename,'sha256':digest}}]}
    path = thumb_dir.parent / 'manifest.json'
    path.write_text(json.dumps(manifest))
    return path, manifest, reel_id, tmp_path / 'destination-thumbs'


def test_import_dry_run_backup_idempotency_and_editorial_preservation(bundle):
    path, _, reel_id, thumbs = bundle
    assert import_catalog(path, settings.DATABASE_PATH, thumbs)['descriptions_added'] == 1
    with get_db_connection() as conn:
        assert conn.execute('SELECT quick_summary FROM reels WHERE id=?',(reel_id,)).fetchone()[0] is None
    result = import_catalog(path, settings.DATABASE_PATH, thumbs, apply=True)
    assert result['descriptions_added'] == result['thumbnails_added'] == result['jobs_reconciled'] == 1
    with sqlite3.connect(result['backup']) as conn:
        assert conn.execute('SELECT quick_summary FROM reels WHERE id=?',(reel_id,)).fetchone()[0] is None
    again = import_catalog(path, settings.DATABASE_PATH, thumbs, apply=True)
    assert again['descriptions_added'] == again['thumbnails_added'] == again['jobs_reconciled'] == 0
    with get_db_connection() as conn:
        row = conn.execute('SELECT * FROM reels WHERE id=?',(reel_id,)).fetchone()
        assert row['quick_summary'] == 'Original description'
        assert row['quick_summary_at'] == 'original-date'
        assert row['notes'] == 'Keep notes' and row['final_post_text'] == 'Keep caption'
        assert row['approved'] == 1 and row['status'] == 'ready'
        assert row['provider_id'] == 'id:a' and row['source_version'] == 'rev1'


def test_import_preserves_newer_description(bundle):
    path, _, reel_id, thumbs = bundle
    with get_db_connection() as conn:
        conn.execute("UPDATE reels SET quick_summary='Newer VM description',quick_summary_at='new-date' WHERE id=?",(reel_id,))
        conn.commit()
    result = import_catalog(path, settings.DATABASE_PATH, thumbs, apply=True)
    assert result['descriptions_added'] == 0 and result['descriptions_preserved'] == 1
    with get_db_connection() as conn:
        assert conn.execute('SELECT quick_summary_at FROM reels WHERE id=?',(reel_id,)).fetchone()[0] == 'new-date'


@pytest.mark.parametrize('mutation', ['revision','duplicate','traversal','hash','processing'])
def test_import_rejects_invalid_or_active_targets(bundle, mutation):
    path, manifest, reel_id, thumbs = bundle
    if mutation == 'revision': manifest['entries'][0]['target']['source_version']='old'
    if mutation == 'duplicate': manifest['entries'] *= 2
    if mutation == 'traversal': manifest['entries'][0]['thumbnail']['filename']='../outside.jpg'
    if mutation == 'hash': manifest['entries'][0]['thumbnail']['sha256']='wrong'
    if mutation == 'processing':
        with get_db_connection() as conn:
            conn.execute("UPDATE summary_jobs SET status='processing' WHERE reel_id=?",(reel_id,)); conn.commit()
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError): import_catalog(path, settings.DATABASE_PATH, thumbs, apply=True)
    with get_db_connection() as conn:
        assert conn.execute('SELECT quick_summary FROM reels WHERE id=?',(reel_id,)).fetchone()[0] is None
