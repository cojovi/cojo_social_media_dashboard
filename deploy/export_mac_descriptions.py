"""Build a conservative description/thumbnail import bundle; never hydrates media.

The VM snapshot is JSON with a `reels` array. Run on the Mac. Only unchanged videos
at matching root-relative paths are eligible; no filename-only or numeric-ID joins.
"""
import argparse
import hashlib
import json
import os
import sqlite3
import stat
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

QUICK = ('quick_summary', 'quick_tags', 'quick_category', 'quick_summary_source',
         'quick_summary_model', 'quick_summary_at')
IDENTITY = ('id', 'provider_id', 'provider_path', 'source_version', 'file_size', 'content_hash')


def normalized(value):
    return unicodedata.normalize('NFC', value).casefold()


def content_hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(4 * 1024 * 1024):
            digest.update(hashlib.sha256(block).digest())
    return digest.hexdigest()


def export(args):
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    (args.output / 'thumbnails').mkdir(mode=0o700)
    with sqlite3.connect(args.database.resolve().as_uri() + '?mode=ro', uri=True) as conn:
        conn.row_factory = sqlite3.Row
        sources = [dict(row) for row in conn.execute('SELECT * FROM reels')]
    index, files = defaultdict(list), defaultdict(list)
    for row in sources:
        try:
            relative = Path(row['filepath']).relative_to(args.source_root).as_posix()
        except ValueError:
            continue
        index[normalized(relative)].append(row)
    for folder, dirs, names in os.walk(args.dropbox_root, followlinks=False):
        dirs[:] = [name for name in dirs if not (Path(folder) / name).is_symlink()]
        for name in names:
            path = Path(folder) / name
            files[normalized(path.relative_to(args.dropbox_root).as_posix())].append(path)
    prefix = normalized(args.provider_root.rstrip('/')) + '/'
    targets = json.loads(args.vm_catalog.read_text())['reels']
    entries, skipped, counts = [], [], Counter()
    for target in targets:
        reason = None
        path = normalized(target.get('provider_path') or '')
        if not path.startswith(prefix):
            reason = 'outside_provider_root'
        else:
            relative = path[len(prefix):]
            matches, locations = index[relative], files[relative]
            if len(matches) != 1 or len(locations) != 1:
                reason = 'missing_or_ambiguous_path'
            else:
                source, local = matches[0], locations[0]
                metadata = local.lstat()
                version = (source['source_version'] or '').split(':')
                if (not stat.S_ISREG(metadata.st_mode) or len(version) != 2
                        or not all(value.isdigit() for value in version)
                        or source['file_size'] != target['file_size']
                        or metadata.st_size != target['file_size']
                        or int(version[0]) != target['file_size']):
                    reason = 'unverified_size_or_version'
                else:
                    delta = abs(metadata.st_mtime_ns - int(version[1]))
                    if delta >= 1_000_000_000:
                        reason = 'modified_since_description'
        if reason:
            skipped.append({'target_id': target['id'], 'reason': reason})
            continue
        method = 'path_size_mtime'
        # UF_DATALESS is macOS's no-content-resident flag. Do not open placeholders.
        if not getattr(metadata, 'st_flags', 0) & 0x40000000 and metadata.st_blocks:
            if not target['content_hash'] or content_hash(local) != target['content_hash']:
                skipped.append({'target_id': target['id'], 'reason': 'content_hash_mismatch'})
                continue
            method += '_content_hash'
            counts['content_hash_verified'] += 1
        counts['metadata_verified'] += 1
        entry = {'target': {key: target[key] for key in IDENTITY},
                 'source': {key: source[key] for key in (*QUICK, 'id', 'filepath', 'source_version')},
                 'match': {'method': method, 'relative_path': relative,
                           'file_size': metadata.st_size, 'mtime_delta_ns': delta}}
        if source['thumbnail_path']:
            asset = args.thumbnails / Path(source['thumbnail_path']).name
            if (asset.is_file() and not asset.is_symlink()
                    and asset.resolve().parent == args.thumbnails.resolve()
                    and asset.stat().st_size <= 10 * 1024 * 1024):
                data = asset.read_bytes()
                digest = hashlib.sha256(data).hexdigest()
                filename = f'mac-import-{digest}.jpg'
                destination = args.output / 'thumbnails' / filename
                if not destination.exists():
                    destination.write_bytes(data)
                entry['thumbnail'] = {'filename': filename, 'sha256': digest}
                counts['with_thumbnail'] += 1
        if source['quick_summary'] or entry.get('thumbnail'):
            entries.append(entry)
            counts['with_description'] += bool(source['quick_summary'])
    manifest = {'version': 1, 'source_database': str(args.database.resolve()),
                'entries': entries, 'skipped': skipped}
    (args.output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False))
    print(json.dumps({'bundle': str(args.output), 'entries': len(entries),
                      'skipped': dict(Counter(item['reason'] for item in skipped)), **counts}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('database', 'source-root', 'dropbox-root', 'thumbnails', 'vm-catalog', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--provider-root', required=True)
    export(parser.parse_args())
