import { useEffect, useState } from 'react';
import { Cloud, HardDrive, ExternalLink, RefreshCw } from 'lucide-react';
import { apiFetch } from './api';
import type { Job, PreviewStorage } from './api';

type StorageStatus = {
  previews?: PreviewStorage;
  provider: string; dropbox: { connected: boolean; folder: string | null };
  cache: { entries: { state: string; files: number; bytes: number }[]; budget_bytes: number; free_disk_bytes: number;
    min_free_disk_bytes: number; ttl_seconds: number; max_downloads: number; active_downloads: number; pinned_files: number };
};
const gb = (bytes: number) => `${(bytes / 1e9).toFixed(2)} GB`;
const inputClass = 'w-full bg-plum-950 border border-plum-700 rounded-lg p-3 text-sm';

export function StoragePanel() {
  const [status, setStatus] = useState<StorageStatus | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [appKey, setAppKey] = useState('');
  const [folder, setFolder] = useState('/Cody Viveiros/SnapTik_Reel_Archive');
  const [flow, setFlow] = useState<{ flow_id: string; authorize_url: string } | null>(null);
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function load() {
    const [storage, recent] = await Promise.all([apiFetch<StorageStatus>('/api/v1/storage'), apiFetch<{ items: Job[] }>('/api/v1/jobs')]);
    setStatus(storage); setJobs(recent.items);
  }
  useEffect(() => {
    let active = true;
    const update = () => { if (active) void load().catch(() => { if (active) setError('Cannot load storage status.'); }); };
    update(); const interval = setInterval(update, 5000);
    return () => { active = false; clearInterval(interval); };
  }, []);
  async function connect() {
    setBusy(true); setError('');
    try {
      if (!flow) setFlow(await apiFetch('/api/v1/storage/dropbox/begin', { method: 'POST', body: JSON.stringify({ app_key: appKey, folder }) }));
      else {
        await apiFetch('/api/v1/storage/dropbox/finish', { method: 'POST', body: JSON.stringify({ flow_id: flow.flow_id, code }) });
        setCode(''); setFlow(null); await load();
      }
    } catch (err) { setError(err instanceof Error ? err.message : 'Connection failed.'); }
    finally { setBusy(false); }
  }
  const cache = status?.cache;
  return <section className="glass-panel rounded-xl border border-plum-800 p-6 flex flex-col gap-5">
    <div className="flex items-center gap-3"><Cloud className="text-neon-cyan" /><h3 className="text-lg font-retro font-bold text-white">Cloud storage & VM</h3></div>
    {cache && <div className="grid grid-cols-2 gap-3 text-sm">
      <div className="bg-plum-950 rounded-lg p-3"><HardDrive size={16} className="text-neon-cyan mb-2" />
        <p className="text-white">{gb(cache.entries.reduce((sum, e) => sum + e.bytes, 0))} / {gb(cache.budget_bytes)}</p><p className="text-purple-400 text-xs">Media cache, including reserved downloads</p></div>
      <div className="bg-plum-950 rounded-lg p-3"><p className="text-white">{gb(cache.free_disk_bytes)} free</p><p className="text-purple-400 text-xs">{gb(cache.min_free_disk_bytes)} protected disk reserve</p></div>
      <p>{cache.active_downloads} / {cache.max_downloads} downloads active</p><p>{cache.ttl_seconds / 3600}h idle expiration · {cache.pinned_files} pinned</p>
    </div>}
    {status?.previews && <div className="border-t border-plum-800 pt-4 flex flex-col gap-3" aria-label="Preview storage">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h4 className="font-semibold text-white">Small video previews</h4>
        <button type="button" disabled={busy} className="text-xs text-neon-cyan underline disabled:opacity-50" onClick={async () => {
          setBusy(true); setError('');
          try {
            await apiFetch('/api/v1/previews/pause', { method: 'POST', body: JSON.stringify({ paused: !status.previews?.paused }) });
            await load();
          } catch { setError('Could not change preview backfill.'); }
          finally { setBusy(false); }
        }}>{status.previews.paused ? 'Resume preview backfill' : 'Pause preview backfill'}</button>
      </div>
      <p className="text-sm text-white">{status.previews.jobs.ready || 0} previews ready · {status.previews.jobs.queued || 0} waiting · {status.previews.jobs.running || 0} preparing · {status.previews.jobs.failed || 0} failed</p>
      <p className="text-xs text-purple-300">{gb(status.previews.bytes + status.previews.reserved_bytes)} / {gb(status.previews.budget_bytes)} on the server, including processing space. Exact copies share a preview.</p>
      <p className="text-xs text-purple-400">Silent samples up to 9 seconds. Backfill continues with the dashboard closed. Click Preview on a reel to give it priority.</p>
      {(status.previews.paused || !status.previews.auto_enabled) && <p className="text-xs text-amber-300">Automatic backfill is paused. Any current clip finishes; requested previews still run.</p>}
      {status.previews.blocked_reason && <p className="text-xs text-amber-300" role="status">{status.previews.blocked_reason}</p>}
    </div>}
    {status?.provider === 'dropbox' && !status.dropbox.connected && <div className="border-t border-plum-800 pt-4 flex flex-col gap-3">
      <h4 className="font-semibold text-white">Connect your Dropbox archive</h4>
      <p className="text-sm text-purple-300">Create a scoped-access app with <strong>Full Dropbox</strong> access in the <a href="https://www.dropbox.com/developers/apps/create" target="_blank" rel="noreferrer" className="text-neon-cyan underline">Dropbox App Console</a>. Enable only <code>account_info.read</code>, <code>files.metadata.read</code> and <code>files.content.read</code>. The backend only indexes the folder below; it never writes to Dropbox.</p>
      {!flow ? <>
        <label className="text-sm">Dropbox app key (not the app secret)<input value={appKey} onChange={e => setAppKey(e.target.value)} className={inputClass} /></label>
        <label className="text-sm">Dropbox-relative archive folder<input value={folder} onChange={e => setFolder(e.target.value)} className={inputClass} /></label>
      </> : <>
        <a href={flow.authorize_url} target="_blank" rel="noreferrer" className="text-neon-cyan underline flex gap-2 items-center">Authorize read-only access in Dropbox <ExternalLink size={14} /></a>
        <p className="text-xs text-purple-300">Dropbox will display a one-time code. Paste it below within 10 minutes. No redirect URL or app secret is required.</p>
        <label className="text-sm">One-time authorization code<input type="password" autoComplete="off" value={code} onChange={e => setCode(e.target.value)} className={inputClass} /></label>
        <button className="text-left text-xs text-purple-400 underline" onClick={() => { setFlow(null); setCode(''); }}>Start over</button>
      </>}
      <button onClick={() => void connect()} disabled={busy || (!flow && !appKey) || (!!flow && !code)} className="rounded-lg bg-neon-cyan text-plum-950 font-bold p-3 cursor-pointer disabled:bg-plum-800 disabled:text-purple-300 disabled:cursor-not-allowed">{busy ? 'Connecting…' : flow ? 'Finish connection' : 'Create authorization link'}</button>
    </div>}
    {status?.dropbox.connected && <p className="text-sm text-green-300">Dropbox connected · {status.dropbox.folder || 'App folder root'}</p>}
    {status?.provider === 'local' && <p className="text-sm text-purple-300">Local mode. Dropbox can be enabled on the VM without changing this Mac’s storage.</p>}
    {error && <p className="text-amber-300 text-sm" role="alert">{error}</p>}
    <div className="border-t border-plum-800 pt-4">
      <div className="flex items-center justify-between mb-3"><h4 className="font-semibold text-white">Background jobs</h4><button aria-label="Refresh jobs" onClick={() => void load().catch(() => setError('Refresh failed.'))}><RefreshCw size={16} /></button></div>
      {!jobs.length && <p className="text-sm text-purple-400">No jobs yet. Downloads, scans and full analysis continue even if you close the dashboard.</p>}
      <div className="flex flex-col gap-2">{jobs.slice(0, 10).map(job => <div key={job.id} className="text-xs bg-plum-950 p-3 rounded-lg">
        <p className="text-purple-200">{job.kind} {job.reel_id ? `· Reel ${job.reel_id}` : ''}<span className="float-right">{job.status}</span></p>
        {job.error && <p className="text-amber-300 mt-1 break-words">{job.error}</p>}
      </div>)}</div>
    </div>
    <button className="text-xs text-purple-400 underline text-left" onClick={() => { void apiFetch('/api/auth/logout', { method: 'POST' }).then(() => window.location.reload()); }}>Sign out of dashboard</button>
  </section>;
}
