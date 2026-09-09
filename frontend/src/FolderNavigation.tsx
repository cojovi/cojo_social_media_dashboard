import { useState } from 'react';
import { ChevronDown, ChevronRight, Folder, FolderOpen, House } from 'lucide-react';
import { folderBreadcrumbs, folderKey } from './folders';
import type { FolderNode, LibraryIndex } from './folders';

interface Props {
  library: LibraryIndex;
  current: FolderNode;
  reelsRoot: string;
  onNavigate: (path: string) => void;
}

export function FolderSidebar({ library, current, reelsRoot, onNavigate }: Props) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const selectedKey = folderKey(current.path, reelsRoot);
  function renderNode(node: FolderNode, depth = 0) {
    const key = folderKey(node.path, reelsRoot);
    const selected = key === selectedKey;
    const ancestor = selectedKey.startsWith(key + '/');
    const open = ancestor || expanded.has(key);
    return <li key={key}>
      <div className={`flex items-center rounded-lg ${selected ? 'bg-neon-cyan/10 text-neon-cyan' : 'text-purple-300 hover:bg-plum-900'}`}
        style={{ paddingLeft: depth * 12 }}>
        {node.children.length > 0 ? <button type="button" aria-label={`${open ? 'Collapse' : 'Expand'} ${node.name}`}
          aria-expanded={open} disabled={ancestor}
          className="p-1.5 rounded focus-visible:outline-neon-cyan disabled:opacity-50"
          onClick={() => setExpanded(previous => {
            const next = new Set(previous);
            if (next.has(key)) next.delete(key); else next.add(key);
            return next;
          })}>
          {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        </button> : <span className="w-[25px] shrink-0" />}
        <button type="button" onClick={() => onNavigate(node.path)} aria-current={selected ? 'location' : undefined}
          className="flex min-w-0 flex-1 items-center gap-2 py-2 pr-2 text-xs text-left rounded focus-visible:outline-neon-cyan"
          title={`${node.name}: ${node.count} unique reels directly in folder; ${node.children.length} subfolders`}>
          {selected ? <FolderOpen size={15} className="shrink-0" /> : <Folder size={15} className="shrink-0" />}
          <span className="truncate flex-1">{node.name}</span>
          <span className="text-[10px] opacity-65 tabular-nums">{node.count}</span>
        </button>
      </div>
      {open && node.children.length > 0 && <ul>{node.children.map(child => renderNode(child, depth + 1))}</ul>}
    </li>;
  }
  return <aside className="hidden xl:flex w-60 shrink-0 glass-panel rounded-xl border border-plum-800 flex-col overflow-hidden">
    <div className="p-4 border-b border-plum-800">
      <p className="text-[10px] uppercase tracking-widest text-purple-400 mb-3">Your library</p>
      <button type="button" onClick={() => onNavigate(library.home.path)}
        aria-current={selectedKey === folderKey(library.home.path, reelsRoot) ? 'location' : undefined}
        className="flex items-center gap-2 text-neon-cyan text-sm font-semibold text-left rounded focus-visible:outline-neon-cyan">
        <House size={17} className="shrink-0" /><span>{library.home.name}</span>
      </button>
      <p className="text-[11px] text-purple-400 mt-2">Home · {library.home.count.toLocaleString()} unique reels</p>
    </div>
    <nav aria-label="Library folders" className="flex-1 overflow-y-auto p-2">
      <p className="text-[10px] uppercase tracking-widest text-purple-400 px-2 py-2">Organize & explore</p>
      <ul>{library.home.children.map(node => renderNode(node))}</ul>
      {library.home !== library.root && <>
        <button type="button" onClick={() => onNavigate('')} className="text-xs text-purple-400 m-2 mt-5 underline">Storage root</button>
        <ul>{library.root.children.filter(node => node !== library.home).map(node => renderNode(node))}</ul>
      </>}
    </nav>
    <p className="p-3 border-t border-plum-800 text-[10px] text-purple-400 leading-relaxed">Counts exclude subfolders and group exact copies. Opening a folder shows only its own reels.</p>
  </aside>;
}

export function FolderLocation({ library, current, reelsRoot, onNavigate }: Props) {
  const crumbs = folderBreadcrumbs(library, current.path, reelsRoot);
  return <section className="mb-5" aria-label="Current folder">
    <nav aria-label="Folder breadcrumb" className="flex items-center flex-wrap gap-1 text-sm mb-3">
      {crumbs.map((node, index) => <span className="flex items-center gap-1" key={node.path}>
        {index > 0 ? <ChevronRight size={14} className="text-purple-500" /> : <House size={15} className="text-neon-cyan mr-1" />}
        <button type="button" onClick={() => onNavigate(node.path)}
          aria-current={index === crumbs.length - 1 ? 'location' : undefined}
          className={`px-2 py-1 rounded hover:bg-plum-800 focus-visible:outline-neon-cyan ${index === crumbs.length - 1 ? 'text-white font-semibold' : 'text-purple-300'}`}>
          {node.name}
        </button>
      </span>)}
    </nav>
    {current.children.length > 0 && <div className="grid grid-cols-[repeat(auto-fill,minmax(185px,1fr))] gap-2 mb-4">
      {current.children.map(node => <button key={node.path} type="button" onClick={() => onNavigate(node.path)}
        className="flex items-center gap-3 p-3 text-left bg-plum-950/60 border border-plum-800 rounded-xl hover:border-neon-cyan/60 hover:bg-plum-900 focus-visible:outline-neon-cyan transition-colors">
        <Folder size={22} className="text-neon-cyan shrink-0" />
        <span className="min-w-0 flex-1"><span className="block text-sm text-purple-100 truncate" title={node.name}>{node.name}</span>
          <span className="block text-[10px] text-purple-400 mt-1">{node.count} reels{node.children.length > 0 ? ` · ${node.children.length} folders` : ''}</span>
        </span><ChevronRight size={14} className="text-purple-400 shrink-0" />
      </button>)}
    </div>}
    <p className="text-xs text-purple-400">Only reels directly in this folder. Subfolder reels stay in their folders.</p>
  </section>;
}
