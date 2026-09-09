import { useEffect, useState } from 'react';
import type { ReactNode, FormEvent } from 'react';
import { LockKeyhole, Film } from 'lucide-react';
import { apiFetch } from './api';

export function AuthGate({ children }: { children: ReactNode }) {
  const [authenticated, setAuthenticated] = useState<boolean | null>(null);
  const [token, setToken] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    apiFetch<{ authenticated: boolean }>('/api/auth/session')
      .then(data => { if (active) setAuthenticated(data.authenticated); })
      .catch(() => { if (active) { setAuthenticated(false); setError('Cannot reach the server. Refresh to retry.'); } });
    const expired = () => { setAuthenticated(false); setToken(''); };
    window.addEventListener('reelvault-session-expired', expired);
    return () => { active = false; window.removeEventListener('reelvault-session-expired', expired); };
  }, []);
  async function login(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('');
    try {
      await apiFetch('/api/auth/login', { method: 'POST', body: JSON.stringify({ token }) });
      setToken(''); setAuthenticated(true);
    } catch (err) { setError(err instanceof Error ? err.message : 'Sign-in failed.'); }
    finally { setBusy(false); }
  }
  if (authenticated) return children;
  return <main className="min-h-screen flex items-center justify-center bg-plum-950 p-6 text-purple-100">
    <div className="glass-panel rounded-2xl border border-plum-700 p-10 w-full max-w-md shadow-2xl">
      <Film className="text-neon-pink mb-5" size={36} />
      <p className="text-xs tracking-[0.3em] uppercase text-purple-400 mb-2">Private archive · VM edition</p>
      <h1 className="font-retro text-3xl text-white mb-3">ReelVault</h1>
      {authenticated === null ? <p role="status">Connecting securely…</p> : <form onSubmit={login} className="flex flex-col gap-4">
        <p className="text-sm text-purple-300 mb-2">Sign in to browse, prepare and manage your reel archive.</p>
        <label className="text-sm font-semibold" htmlFor="access-token">Owner access token</label>
        <input id="access-token" type="password" autoComplete="current-password" required value={token}
          onChange={e => setToken(e.target.value)} className="bg-plum-950 border border-plum-700 rounded-lg p-3 focus:outline-neon-pink" />
        {error && <p role="alert" className="text-amber-300 text-sm">{error}</p>}
        <button disabled={busy} className="bg-neon-pink text-plum-950 font-bold rounded-lg px-4 py-3 flex items-center justify-center gap-2 disabled:opacity-50">
          <LockKeyhole size={16} />{busy ? 'Signing in…' : 'Unlock archive'}
        </button>
        <p className="text-xs text-purple-400">Your token stays out of browser storage. Sessions expire after 24 hours or a server restart.</p>
      </form>}
    </div>
  </main>;
}
