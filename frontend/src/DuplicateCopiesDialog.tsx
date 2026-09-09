import { useEffect, useRef, useState } from 'react';
import { Copy, X } from 'lucide-react';
import type { LibraryItem } from './api';
import { getRelativeFolder } from './folders';

export function DuplicateCopiesDialog({ copies, reelsRoot, onClose, onOpen }: {
  copies: LibraryItem[];
  reelsRoot: string;
  onClose: () => void;
  onOpen: (id: number) => Promise<boolean>;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => element?.close();
  }, []);
  return <dialog ref={dialog} onCancel={onClose} aria-labelledby="copies-heading"
    className="m-auto w-[min(640px,92vw)] max-h-[85vh] overflow-auto rounded-2xl border border-plum-700 bg-plum-950 text-purple-100 p-6 shadow-2xl backdrop:bg-black/75">
    <div className="flex items-center justify-between gap-3 mb-3">
      <h2 id="copies-heading" className="text-lg font-semibold flex items-center gap-2"><Copy size={20} className="text-neon-cyan" />Exact copies · {copies.length}</h2>
      <button type="button" onClick={onClose} aria-label="Close copies" className="p-2 rounded hover:bg-plum-800 focus-visible:outline-neon-cyan"><X size={18} /></button>
    </div>
    <p className="text-sm text-purple-300 mb-4">These files have the same Dropbox content hash and size. Nothing has been deleted or merged. Each copy keeps its own notes, caption, approval and status.</p>
    <p className="text-xs text-purple-400 mb-4">All locations are listed below, including copies outside the current folder or filters. Open a copy to view or edit its record.</p>
    {error && <p role="alert" className="text-red-300 text-sm mb-3">{error}</p>}
    <ul className="space-y-2">
      {copies.map(copy => <li key={copy.id} className="p-3 rounded-lg border border-plum-800 flex items-center gap-3">
        <div className="flex-1 min-w-0">
          <p className="text-sm break-all">{copy.filename}</p>
          <p className="text-xs text-purple-400 break-all mt-1">{getRelativeFolder(copy.filepath, reelsRoot) || 'Source root'}</p>
          <p className="text-[10px] text-purple-400 mt-1">ID {copy.id} · {copy.status.replace('_', ' ')}</p>
        </div>
        <button type="button" disabled={busy !== null} className="archive-button shrink-0 disabled:opacity-50" onClick={async () => {
          setBusy(copy.id); setError('');
          try {
            if (await onOpen(copy.id)) onClose();
            else setError('Save the current workbench changes before opening another copy.');
          } catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not open this copy.'); }
          finally { setBusy(null); }
        }}>{busy === copy.id ? 'Opening…' : 'Open'}</button>
      </li>)}
    </ul>
  </dialog>;
}
