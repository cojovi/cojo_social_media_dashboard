import assert from 'node:assert/strict';
import { test } from 'node:test';
import { buildLibraryIndex, exactCopyKey, filterReelsByFolder, folderBreadcrumbs,
  folderKey, getRelativeFolder, groupExactCopies } from '../src/folders.ts';

const root = 'dropbox:/Cody Viveiros/SnapTik_Reel_Archive';
const home = 'SnapIGTik Download';
const hash = 'a'.repeat(64);
const item = (id, folder = home, extra = {}) => ({
  id, filename: `${id}.mp4`, filepath: `${root}/${folder}/${id}.mp4`,
  file_size: 100, storage_provider: 'dropbox', content_hash: null, status: 'draft', storage_status: 'cloud', ...extra,
});
const items = [item(1), item(2, `${home}/artistic/tv`), item(3, `${home}/artistic/landscape`),
  item(4, `${home}/image prompts`), item(5, `${home}/artistic`), item(6, '', { filepath: `${root}/6.mp4` })];

test('home resolves through the Dropbox wrapper and excludes ALL subfolder reels', () => {
  const library = buildLibraryIndex(items, root);
  assert.equal(library.home.path, home);
  assert.deepEqual(filterReelsByFolder(items, root, library.home.path).map(r => r.id), [1]);
  assert.equal(library.home.count, 1);
  assert.equal(library.root.count, 1);
});

test('opening an intermediate folder shows its own reels, not descendants', () => {
  assert.deepEqual(filterReelsByFolder(items, root, `${home}/artistic`).map(r => r.id), [5]);
  assert.deepEqual(filterReelsByFolder(items, root, `${home}/artistic/tv`).map(r => r.id), [2]);
  const library = buildLibraryIndex(items, root);
  const artistic = library.nodes.get(folderKey(`${home}/artistic`, root));
  assert.equal(artistic.count, 1);
  assert.deepEqual(artistic.children.map(r => r.name), ['landscape', 'tv']);
});

test('parents with no direct videos still expose child folders and breadcrumbs', () => {
  const library = buildLibraryIndex([items[1]], root);
  assert.equal(library.home.count, 0);
  assert.equal(library.home.children[0].count, 0);
  assert.deepEqual(folderBreadcrumbs(library, `${home}/artistic/tv`, root).map(n => n.name),
    [home, 'artistic', 'tv']);
  assert.deepEqual(folderBreadcrumbs(library, home, root).map(n => n.name), [home]);
});

test('local source already named SnapIGTik Download uses direct source root', () => {
  const localRoot = '/Users/test/SnapIGTik Download';
  const rows = [item(1, '', { filepath: `${localRoot}/a.mp4`, storage_provider: 'local' }),
    item(2, '', { filepath: `${localRoot}/artistic/a.mp4`, storage_provider: 'local' })];
  const library = buildLibraryIndex(rows, localRoot);
  assert.equal(library.home.path, '');
  assert.deepEqual(filterReelsByFolder(rows, localRoot, '').map(r => r.id), [1]);
});

test('Dropbox case and Unicode normalization do not split folder identities', () => {
  const rows = [item(1, `${home}/Cafe\u0301`), item(2, `${home.toLowerCase()}/Café`)];
  const library = buildLibraryIndex(rows, root);
  assert.equal(library.home.children.length, 1);
  assert.equal(library.home.children[0].count, 2);
  assert.equal(filterReelsByFolder(rows, root.toLowerCase(), `${home}/CAFÉ`).length, 2);
});

test('source and folder prefix boundaries exclude unrelated locations', () => {
  const rows = [...items, item(99, home, { filepath: `${root}-old/${home}/99.mp4` })];
  assert.equal(getRelativeFolder(rows.at(-1).filepath, root), 'Previous source');
  assert.deepEqual(filterReelsByFolder(rows, root, home).map(r => r.id), [1]);
  assert.deepEqual(filterReelsByFolder(rows, root, `${home}/art`).map(r => r.id), []);
  assert.notEqual(folderKey('Art', '/local'), folderKey('art', '/local'));
});

test('exact copies collapse deterministically, preferring concise original name', () => {
  const rows = [item(1206, home, { filename: 'Number copy.mp4', content_hash: hash }),
    item(1205, home, { filename: 'Number.mp4', content_hash: hash }),
    item(1204, home, { filename: 'Number copy 2.mp4', content_hash: hash })];
  const original = JSON.stringify(rows);
  assert.deepEqual(groupExactCopies(rows).map(r => r.id), [1205]);
  assert.deepEqual(groupExactCopies([...rows].reverse()).map(r => r.id), [1205]);
  assert.equal(JSON.stringify(rows), original);
  const library = buildLibraryIndex(rows, root);
  assert.equal(library.home.count, 1);
  assert.equal(library.home.fileCount, 3);
  assert.deepEqual(library.copies.get(exactCopyKey(rows[0])).map(r => r.id), [1206, 1205, 1204]);
});

test('similar previews, different edits, malformed/missing hashes never auto-merge', () => {
  const rows = [item(1, home, { content_hash: hash }), item(2, home, { content_hash: 'b'.repeat(64) }),
    item(3, home, { content_hash: hash, file_size: 200 }), item(4), item(5),
    item(6, home, { content_hash: 'bad' }), item(7, home, { content_hash: 'bad' }),
    item(8, home, { content_hash: hash, storage_provider: 'local' }),
    item(9, home, { content_hash: hash, file_size: 0 })];
  assert.equal(groupExactCopies(rows).length, rows.length);
});

test('cross-folder copies stay visible in each location; copy index retains every ID', () => {
  const rows = [item(1, home, { content_hash: hash }), item(2, `${home}/artistic`, { content_hash: hash })];
  const library = buildLibraryIndex(rows, root);
  assert.deepEqual(groupExactCopies(filterReelsByFolder(rows, root, home)).map(r => r.id), [1]);
  assert.deepEqual(groupExactCopies(filterReelsByFolder(rows, root, `${home}/artistic`)).map(r => r.id), [2]);
  assert.equal(library.copies.get(exactCopyKey(rows[0])).length, 2);
});

test('search/status filtering before grouping retains matching copies and does not prune navigation', () => {
  const rows = [item(1, home, { content_hash: hash, status: 'draft' }),
    item(2, home, { content_hash: hash, status: 'ready' }), item(3, `${home}/image prompts`)];
  const library = buildLibraryIndex(rows, root);
  assert.deepEqual(groupExactCopies(rows.filter(r => r.status === 'ready')).map(r => r.id), [2]);
  assert.deepEqual(groupExactCopies(rows.filter(r => r.id === 1)).map(r => r.id), [1]);
  assert.equal(library.home.children[0].name, 'image prompts');
  assert.equal(library.copies.get(exactCopyKey(rows[0])).length, 2);
});

test('empty catalogs and generic sources have safe direct-root defaults', () => {
  const library = buildLibraryIndex([], '/library');
  assert.equal(library.home.path, '');
  assert.equal(library.home.name, 'library');
  assert.deepEqual(groupExactCopies([]), []);
  assert.deepEqual(filterReelsByFolder([], '/library', ''), []);
});

test('missing records do not leave ghost folders, counts, or duplicate copies', () => {
  const rows = [item(1, home, { content_hash: hash }),
    item(2, home, { content_hash: hash, storage_status: 'missing' }),
    item(3, `${home}/deleted folder`, { storage_status: 'missing' })];
  const library = buildLibraryIndex(rows, root);
  assert.equal(library.home.fileCount, 1);
  assert.equal(library.home.count, 1);
  assert.equal(library.home.children.length, 0);
  assert.deepEqual(library.copies.get(exactCopyKey(rows[0])).map(r => r.id), [1]);
  const history = buildLibraryIndex(rows, root, true);
  assert.equal(history.home.children[0].name, 'deleted folder');
  assert.equal(history.home.fileCount, 2);
});

test('a rescan updates direct membership and filename while retaining the reel ID', () => {
  const initial = [item(1, home)];
  const moved = [item(1, `${home}/organized`, { filename: 'new name.mp4',
    filepath: `${root}/${home}/organized/new name.mp4` })];
  assert.equal(buildLibraryIndex(initial, root).home.count, 1);
  const library = buildLibraryIndex(moved, root);
  assert.equal(library.home.count, 0);
  assert.deepEqual(filterReelsByFolder(moved, root, home), []);
  assert.equal(filterReelsByFolder(moved, root, `${home}/organized`)[0].filename, 'new name.mp4');
  assert.equal(library.home.children[0].count, 1);
});
