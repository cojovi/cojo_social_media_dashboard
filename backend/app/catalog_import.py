"""Offline, additive import of verified Mac descriptions into the Dropbox catalog.

Run with the service stopped. This never imports IDs, approval, captions, source paths,
provider identity, usage charges, or queue leases from the old catalog. The local
exporter must verify root-relative path, size and source mtime before making a manifest.
"""
import argparse
import hashlib
import json
import re
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

QUICK_FIELDS = ('quick_summary', 'quick_tags', 'quick_category', 'quick_summary_source',
                'quick_summary_model', 'quick_summary_at')
IDENTITY_FIELDS = ('provider_id', 'provider_path', 'source_version', 'file_size', 'content_hash')


def import_catalog(manifest_path, database_path, thumbnails_path, *, apply=False):
    manifest_path, database_path, thumbnails_path = map(Path, (manifest_path, database_path, thumbnails_path))
    raw = manifest_path.read_bytes()
    manifest = json.loads(raw)
    if manifest.get('version') != 1:
        raise ValueError('Unsupported import manifest')
    conn = sqlite3.connect(database_path.resolve().as_uri() + ('?mode=rw' if apply else '?mode=ro'), uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    actions, seen = [], set()
    counts = dict(matched=0, descriptions_added=0, descriptions_preserved=0, thumbnails_added=0, jobs_reconciled=0)
    try:
        for entry in manifest['entries']:
            target = entry['target']
            if target['id'] in seen:
                raise ValueError('Duplicate destination ID in manifest')
            seen.add(target['id'])
            current = conn.execute('SELECT * FROM reels WHERE id=?', (target['id'],)).fetchone()
            if (not current or current['storage_provider'] != 'dropbox'
                    or any(current[field] != target[field] for field in IDENTITY_FIELDS)):
                raise ValueError(f"Destination identity/revision changed: {target['id']}")
            proof = entry['match']
            if (proof['method'] not in {'path_size_mtime', 'path_size_mtime_content_hash'}
                    or proof['file_size'] != current['file_size']
                    or not 0 <= proof['mtime_delta_ns'] < 1_000_000_000):
                raise ValueError('Missing file identity evidence')
            source = entry['source']
            counts['matched'] += 1
            values = {}
            if source.get('quick_summary') and not current['quick_summary']:
                for field in QUICK_FIELDS:
                    value = source.get(field)
                    if value is not None and not isinstance(value, str):
                        raise ValueError('Description fields must be strings or null')
                    values[field] = value
                counts['descriptions_added'] += 1
            elif current['quick_summary']:
                counts['descriptions_preserved'] += 1
            thumbnail = entry.get('thumbnail')
            asset = None
            existing = current['thumbnail_path']
            if thumbnail and (not existing or not (thumbnails_path / Path(existing).name).is_file()):
                filename = thumbnail['filename']
                if not re.fullmatch(r'mac-import-[a-f0-9]{64}\.jpg', filename):
                    raise ValueError('Unsafe thumbnail name')
                asset = manifest_path.parent / 'thumbnails' / filename
                if asset.is_symlink() or asset.resolve().parent != (manifest_path.parent / 'thumbnails').resolve():
                    raise ValueError('Unsafe thumbnail path')
                if hashlib.sha256(asset.read_bytes()).hexdigest() != thumbnail['sha256']:
                    raise ValueError('Thumbnail integrity mismatch')
                destination = thumbnails_path / filename
                if destination.exists() and (destination.is_symlink() or hashlib.sha256(destination.read_bytes()).hexdigest() != thumbnail['sha256']):
                    raise ValueError('Existing thumbnail conflicts with import')
                values['thumbnail_path'] = filename
                counts['thumbnails_added'] += 1
            described = bool(current['quick_summary'] or values.get('quick_summary'))
            job = conn.execute('SELECT status FROM summary_jobs WHERE reel_id=?', (target['id'],)).fetchone()
            finish_job = bool(described and job and job['status'] != 'done')
            counts['jobs_reconciled'] += int(finish_job)
            actions.append((target['id'], values, asset, finish_job))
        if not apply:
            return {'dry_run': True, **counts}
        # Stop workers before applying; SQLite backup includes the entire current catalog.
        if conn.execute("SELECT COUNT(*) FROM summary_jobs WHERE status='processing'").fetchone()[0]:
            raise ValueError('A summary job is still processing; wait for completion before importing')
        backup_dir = database_path.parent / 'backups'
        backup_dir.mkdir(mode=0o700, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        backup_path = backup_dir / f'reelvault-before-mac-descriptions-{stamp}.db'
        with sqlite3.connect(backup_path) as backup:
            conn.backup(backup)
        backup_path.chmod(0o600)
        thumbnails_path.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        with conn:
            conn.execute('BEGIN IMMEDIATE')
            for reel_id, values, asset, finish_job in actions:
                if asset:
                    destination = thumbnails_path / values['thumbnail_path']
                    if not destination.exists():
                        with destination.open('xb') as output, asset.open('rb') as source:
                            shutil.copyfileobj(source, output)
                if values:
                    fields = ','.join(f'{key}=?' for key in values)
                    conn.execute(f'UPDATE reels SET {fields} WHERE id=?', (*values.values(), reel_id))
                if finish_job:
                    conn.execute("UPDATE summary_jobs SET status='done',error=NULL,available_at=0,updated_at=? WHERE reel_id=?", (now, reel_id))
            conn.execute('INSERT OR REPLACE INTO archive_state(key,value) VALUES (?,?)',
                         ('mac_description_import:' + hashlib.sha256(raw).hexdigest(),
                          json.dumps({'applied_at': now, 'source_database': manifest.get('source_database'), **counts})))
        return {'dry_run': False, 'backup': str(backup_path), **counts}
    finally:
        conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--thumbnails', type=Path, required=True)
    parser.add_argument('--apply', action='store_true', help='Write after validation and backup; default is dry-run')
    args = parser.parse_args()
    print(json.dumps(import_catalog(args.manifest, args.database, args.thumbnails, apply=args.apply)))
