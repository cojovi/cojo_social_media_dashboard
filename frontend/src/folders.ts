import type { Reel } from './api';

export interface FolderNode {
  name: string;
  path: string;
  count: number;
  children: FolderNode[];
}

/** Relative folder path inside the reels root (empty string = file at root). */
export function getRelativeFolder(filepath: string, reelsRoot: string): string {
  const normalizedRoot = reelsRoot.replace(/\/+$/, '');
  let rel = filepath;
  if (filepath.startsWith(normalizedRoot)) {
    rel = filepath.slice(normalizedRoot.length).replace(/^\/+/, '');
  }
  const lastSlash = rel.lastIndexOf('/');
  return lastSlash === -1 ? '' : rel.slice(0, lastSlash);
}

export function buildFolderTree(reels: Reel[], reelsRoot: string): FolderNode[] {
  const directCounts = new Map<string, number>();

  for (const reel of reels) {
    const folder = getRelativeFolder(reel.filepath, reelsRoot);
    directCounts.set(folder, (directCounts.get(folder) || 0) + 1);
  }

  const nodeMap = new Map<string, FolderNode>();

  const ensureNode = (path: string, name: string): FolderNode => {
    const existing = nodeMap.get(path);
    if (existing) return existing;
    const node: FolderNode = {
      name,
      path,
      count: 0,
      children: [],
    };
    nodeMap.set(path, node);
    return node;
  };

  ensureNode('', 'Root');

  for (const [folderPath, count] of directCounts) {
    if (folderPath === '') {
      nodeMap.get('')!.count = count;
      continue;
    }

    const parts = folderPath.split('/');
    let currentPath = '';
    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      const parentPath = currentPath;
      currentPath = currentPath ? `${currentPath}/${part}` : part;
      const node = ensureNode(currentPath, part);
      if (i === parts.length - 1) {
        node.count = count;
      }
      if (parentPath !== currentPath) {
        const parent = ensureNode(parentPath, parentPath === '' ? 'Root' : parentPath.split('/').pop()!);
        if (!parent.children.some(c => c.path === node.path)) {
          parent.children.push(node);
        }
      }
    }
  }

  const sortNodes = (nodes: FolderNode[]) => {
    nodes.sort((a, b) => a.name.localeCompare(b.name));
    nodes.forEach(n => sortNodes(n.children));
  };

  const root = nodeMap.get('')!;
  sortNodes(root.children);
  return root.children;
}

/** Match reels in the selected folder and all nested subfolders. */
export function filterReelsByFolder(reels: Reel[], reelsRoot: string, folderPath: string | null): Reel[] {
  if (folderPath === null) return reels;

  return reels.filter(reel => {
    const folder = getRelativeFolder(reel.filepath, reelsRoot);
    if (folderPath === '') {
      return folder === '';
    }
    return folder === folderPath || folder.startsWith(`${folderPath}/`);
  });
}

export function countReelsInFolder(reels: Reel[], reelsRoot: string, folderPath: string | null): number {
  return filterReelsByFolder(reels, reelsRoot, folderPath).length;
}
