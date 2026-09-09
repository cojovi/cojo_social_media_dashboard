import { useState } from 'react';
import { Cloud, RefreshCw, Pause, Play, Sparkles } from 'lucide-react';
import { api, type ArchiveStatus } from './api';

type Props = {
  status: ArchiveStatus | null;
  onRefresh: () => void;
  onToast: (message: string, type: 'success' | 'error' | 'warning') => void;
  onScan: () => void;
};

export function ArchivePanel({ status, onRefresh, onToast, onScan }: Props) {
  const [busy, setBusy] = useState(false);
  if (!status) return null;
  const run = async (action: () => Promise<unknown>) => {
    setBusy(true);
    try { await action(); onRefresh(); }
    catch (e) { onToast(e instanceof Error ? e.message : 'Archive action failed.', 'error'); }
    finally { setBusy(false); }
  };
  const queue = () => run(async () => {
    const result = await api.describeMissing(undefined, true);
    onToast(`${result.queued} descriptions queued. Work continues while the backend is running.`, 'success');
  });
  return (
    <section className="glass-panel rounded-xl border border-plum-700 p-5 flex flex-col gap-4" aria-label="Archive automation">
      <div className="flex items-center gap-2 text-neon-cyan">
        <Cloud className="w-5 h-5" /><h3 className="font-semibold">Archive automation</h3>
      </div>
      <p className="text-sm text-purple-200 leading-relaxed">
        {status.auto_scan ? `Scans at startup and every ${Math.round(status.scan_interval_seconds / 60)} minutes.` : 'Automatic scanning is off.'}
        {' '}Browsing uses cached images. Videos download when you choose to play, download or process them.
      </p>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
        {[[status.described, 'Described'], [status.storage.local || 0, 'Local sources'],
          [status.storage.cloud || 0, status.storage_provider === 'dropbox' ? 'In Dropbox' : 'Offloaded'], [status.storage.missing || 0, 'Missing / moved']].map(([value, label]) => (
          <div key={label} className="rounded-lg bg-plum-950 p-3 border border-plum-800">
            <p className="text-white text-xl font-semibold">{value}</p><p className="text-xs text-purple-400">{label}</p>
          </div>
        ))}
      </div>
      <p className="text-xs text-purple-300">
        {status.scan.running ? 'Scanning folder…' : status.scan.finished_at ? `Last scan: ${new Date(status.scan.finished_at).toLocaleString()} · ${status.scan.added || 0} new` : 'Waiting for first scan'}
        {Boolean(status.scan.skipped) && ` · ${status.scan.skipped} files empty or still arriving`}
      </p>
      {status.scan.error && <p role="alert" className="text-sm text-amber-300">{status.scan.error}</p>}
      <div className="border-t border-plum-800 pt-4 flex flex-col gap-2">
        <h4 className="text-sm font-semibold text-white">Quick descriptions · {status.paused ? 'Paused' : status.blocked_reason ? 'Waiting' : 'Active'}</h4>
        <p className="text-xs text-purple-300 leading-relaxed">
          Three small frames from local videos, or one existing thumbnail for offloaded videos. Rough visual labels only; no audio review.
          {status.storage_provider === 'dropbox' && ' Queued Dropbox videos are downloaded through the bounded cache for frame sampling.'}
          {' '}{status.auto_quick_summary ? 'New discoveries join this queue automatically.' : 'Automatic descriptions are off; use the queue button below.'}
        </p>
        <p className="text-xs text-purple-400 break-all">{status.quick_model}</p>
        <p className="text-sm text-purple-200">
          {status.jobs.done || 0} done · {status.jobs.queued || 0} queued · {status.jobs.processing || 0} processing · {status.jobs.waiting_local || 0} waiting for a local preview · {status.jobs.failed || 0} failed
        </p>
        <p className="text-xs text-purple-300">
          Estimated API use since tracking began: ${status.usage.estimated_cost_usd.toFixed(4)} · {status.usage.requests} requests.
          {' '}Quick descriptions today: ${status.usage.quick_today_usd.toFixed(4)} / ${status.usage.quick_daily_budget_usd.toFixed(2)} daily estimate limit (UTC).
        </p>
        <p className="text-[11px] text-purple-400">Estimates use paid token rates; your Google bill may differ. Older analyses have no recorded usage. Full video reviews are separate from the quick-description limit.</p>
        {status.blocked_reason && <p role="status" className="text-xs text-amber-300">{status.blocked_reason}</p>}
      </div>
      <div className="flex flex-wrap gap-2">
        <button onClick={onScan} disabled={status.scan.running} className="archive-button"><RefreshCw className="w-4 h-4" /> Scan now</button>
        <button onClick={queue} disabled={busy} className="archive-button"><Sparkles className="w-4 h-4" /> Describe missing / retry</button>
        <button onClick={() => run(() => api.pauseDescriptions(!status.paused))} disabled={busy} className="archive-button">
          {status.paused ? <Play className="w-4 h-4" /> : <Pause className="w-4 h-4" />}{status.paused ? 'Resume descriptions' : 'Pause descriptions'}
        </button>
      </div>
      {status.recent_jobs.some(j => j.error) && (
        <details className="text-xs text-purple-300">
          <summary className="cursor-pointer">Files needing attention</summary>
          <div className="mt-2 flex flex-col gap-2">
            {status.recent_jobs.filter(j => j.error).map(j => <p key={j.reel_id} className="break-words"><strong>{j.filename}</strong> · {j.error}</p>)}
          </div>
        </details>
      )}
    </section>
  );
}
