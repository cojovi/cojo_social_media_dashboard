import type { LibraryItem } from './api';

export interface FolderNode {
  name: string;
  path: string;
  /** Unique exact-copy groups directly in this folder, not descendants. */
  count: number;
  fileCount: number;
  children: FolderNode[];
}

/** Dropbox paths are case-insensitive; local paths are not assumed to be. */
export function folderKey(path: string, reelsRoot: string): string {
  const normalized = path.normalize('NFC').replace(/\/+$/, '');
  return reelsRoot.startsWith('dropbox:') ? normalized.toLowerCase() : normalized;
}

/** Relative folder inside the configured source (empty string = source root). */
export function getRelativeFolder(filepath: string, reelsRoot: string): string {
  const root = reelsRoot.normalize('NFC').replace(/\/+$/, '');
  const file = filepath.normalize('NFC');
  if (root && !folderKey(file, root).startsWith(folderKey(root, root) + '/')) return 'Previous source';
  const relative = root ? file.slice(root.length + 1) : file;
  const lastSlash = relative.lastIndexOf('/');
  return lastSlash === -1 ? '' : relative.slice(0, lastSlash);
}

/** Only provider content hashes prove identical bytes; names/previews do not. */
export function exactCopyKey(reel: Pick<LibraryItem, 'id' | 'storage_provider' | 'content_hash' | 'file_size'>): string {
  if (reel.storage_provider === 'dropbox' && /^[a-f\d]{64}$/i.test(reel.content_hash || '') && reel.file_size > 0) {
    return `dropbox:${reel.content_hash!.toLowerCase()}:${reel.file_size}`;
  }
  return `record:${reel.id}`;
}

export function indexCopies<T extends LibraryItem>(reels: T[]): Map<string, T[]> {
  const groups = new Map<string, T[]>();
  for (const reel of reels) {
    const key = exactCopyKey(reel);
    const group = groups.get(key);
    if (group) group.push(reel);
    else groups.set(key, [reel]);
  }
  return groups;
}

/** Preserve query order and folder membership. Every underlying ID stays intact. */
export function groupExactCopies<T extends LibraryItem>(reels: T[]): T[] {
  return [...indexCopies(reels).values()].map(group => group.reduce((best, reel) => {
    // Prefer the concise original name over "copy 2", with a stable ID tie-break.
    return reel.filename.length < best.filename.length ||
      (reel.filename.length === best.filename.length && reel.id < best.id) ? reel : best;
  }));
}

/** Direct children only, never a recursive view. */
export function filterReelsByFolder<T extends LibraryItem>(reels: T[], reelsRoot: string, folderPath: string): T[] {
  const selected = folderKey(folderPath, reelsRoot);
  return reels.filter(reel => folderKey(getRelativeFolder(reel.filepath, reelsRoot), reelsRoot) === selected);
}

/** One catalog pass builds stable navigation even while the grid is filtered. */
export function buildLibraryIndex(reels: LibraryItem[], reelsRoot: string, includeMissing = false) {
  // Missing paths are history, not current folder membership or available copies.
  const members = includeMissing ? reels : reels.filter(reel => reel.storage_status !== 'missing');
  const nodes = new Map<string, FolderNode>();
  const identities = new Map<string, Set<string>>();
  const ensure = (path: string): FolderNode => {
    const key = folderKey(path, reelsRoot);
    const existing = nodes.get(key);
    if (existing) return existing;
    const node: FolderNode = {
      name: path.split('/').pop() || reelsRoot.replace(/\/+$/, '').split('/').pop() || 'Library',
      path, count: 0, fileCount: 0, children: [],
    };
    nodes.set(key, node);
    if (path) {
      const slash = path.lastIndexOf('/');
      ensure(slash < 0 ? '' : path.slice(0, slash)).children.push(node);
    }
    return node;
  };
  const root = ensure('');
  for (const reel of members) {
    const path = getRelativeFolder(reel.filepath, reelsRoot);
    const node = ensure(path);
    node.fileCount++;
    const key = folderKey(path, reelsRoot);
    let seen = identities.get(key);
    if (!seen) { seen = new Set(); identities.set(key, seen); }
    seen.add(exactCopyKey(reel));
    node.count = seen.size;
  }
  for (const node of nodes.values()) node.children.sort((a, b) => a.name.localeCompare(b.name));
  // The Dropbox source wraps the old Mac root by one level. Generic roots work too.
  const home = root.name.toLowerCase() === 'snapigtik download' ? root :
    root.children.find(node => node.name.toLowerCase() === 'snapigtik download') || root;
  return { root, home, nodes, copies: indexCopies(members) };
}

export type LibraryIndex = ReturnType<typeof buildLibraryIndex>;

export function folderBreadcrumbs(library: LibraryIndex, path: string, reelsRoot: string): FolderNode[] {
  const selected = folderKey(path, reelsRoot);
  const homeKey = folderKey(library.home.path, reelsRoot);
  const inHome = !homeKey || selected === homeKey || selected.startsWith(homeKey + '/');
  const start = inHome ? library.home : library.root;
  const result = [start];
  let current = start.path;
  const rest = path.slice(current ? current.length + 1 : 0);
  if (selected === folderKey(current, reelsRoot)) return result;
  for (const part of rest.split('/').filter(Boolean)) {
    current = current ? `${current}/${part}` : part;
    const node = library.nodes.get(folderKey(current, reelsRoot));
    if (node) result.push(node);
  }
  return result;
}
