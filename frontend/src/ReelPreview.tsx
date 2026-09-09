import { useEffect, useRef, useState } from 'react';
import { Loader2, X } from 'lucide-react';
import { apiFetch } from './api';
import type { PreviewInfo } from './api';

// Mounted only after an intentional click. No per-card polling, hover downloads or hidden players.
export function ReelPreview({ reelId, filename, onClose, onFullVideo }: {
  reelId: number; filename: string; onClose: () => void; onFullVideo: () => void;
}) {
  const [preview, setPreview] = useState<PreviewInfo | null>(null);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const container = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    const deadline = Date.now() + 10 * 60 * 1000;
    const update = async (request: boolean) => {
      try {
        const result = await apiFetch<PreviewInfo>(`/api/v1/reels/${reelId}/preview`, {
          method: request ? 'POST' : 'GET', signal: controller.signal,
        });
        if (controller.signal.aborted) return;
        setPreview(result);
        if (result.status === 'queued' || result.status === 'running') {
          if (Date.now() > deadline) setError('This is still preparing on the server. You can close this and return later.');
          else timer = setTimeout(() => void update(false), 2000);
        } else if (result.status !== 'ready') {
          setError(result.error || 'Preview unavailable. Try again or open the full video.');
        }
      } catch (err) {
        if (!controller.signal.aborted) setError(err instanceof Error ? err.message : 'Could not load preview.');
      }
    };
    void update(true);
    return () => { controller.abort(); clearTimeout(timer); };
  }, [reelId, attempt]);

  useEffect(() => {
    const observer = new IntersectionObserver(entries => {
      if (entries[0] && !entries[0].isIntersecting) onClose();
    });
    if (container.current) observer.observe(container.current);
    const hidden = () => { if (document.hidden) onClose(); };
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose(); };
    document.addEventListener('visibilitychange', hidden);
    window.addEventListener('keydown', escape);
    return () => {
      observer.disconnect(); document.removeEventListener('visibilitychange', hidden);
      window.removeEventListener('keydown', escape);
    };
  }, [onClose]);

  return <div ref={container} className="absolute inset-0 z-30 bg-black flex flex-col" onClick={event => event.stopPropagation()}
    role="region" aria-label={`Preview of ${filename}`}>
    <div className="flex items-center justify-between gap-2 px-3 py-2 bg-plum-950 text-neon-cyan text-[11px]">
      <span>Sampled preview · No audio</span>
      <button type="button" autoFocus onClick={onClose} className="p-1 rounded hover:bg-white/10 focus-visible:outline-neon-cyan" aria-label="Close preview"><X size={17} /></button>
    </div>
    {preview?.status === 'ready' && preview.url && !error ? <video key={preview.key}
      src={preview.url} muted autoPlay loop playsInline controls preload="none"
      aria-label={`Sampled preview of ${filename}`} className="w-full min-h-0 flex-1 object-contain"
      onError={() => setError('This preview could not play. Retry to refresh it, or open the full video.')} /> :
      <div className="min-h-0 flex-1 flex flex-col items-center justify-center p-4 gap-3 text-center text-xs text-purple-200" role="status">
        {!error && <Loader2 className="animate-spin text-neon-cyan" size={24} />}
        <p>{error || (preview?.status === 'running' ? 'Creating your preview…' : 'Preparing your preview…')}</p>
        {!error && <p className="text-purple-400">{preview?.error || 'First preview can take a moment. You can keep browsing.'}</p>}
        {error && <button type="button" className="text-neon-cyan underline" onClick={() => {
          setError(''); setPreview(null); setAttempt(value => value + 1);
        }}>Retry preview</button>}
      </div>}
    <button type="button" onClick={onFullVideo} className="px-3 py-2.5 bg-plum-950 border-t border-plum-700 text-xs text-neon-cyan hover:bg-plum-800 focus-visible:outline-neon-cyan">
      Open full video with audio
    </button>
  </div>;
}
