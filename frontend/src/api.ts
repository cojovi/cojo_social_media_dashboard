export interface Reel {
  id: number;
  filename: string;
  filepath: string;
  file_extension: string;
  file_size: number;
  storage_provider: 'local' | 'dropbox';
  content_hash: string | null;
  source_version: string | null;
  duration_seconds: number;
  thumbnail_path: string | null;
  created_at: string;
  updated_at: string;
  discovered_at: string;
  status: 'draft' | 'needs_review' | 'ready' | 'posted' | 'archived';
  approved: boolean;
  manual_post_text: string | null;
  final_post_text: string | null;
  hashtags: string | null;
  notes: string | null;
  ai_summary: string | null;
  ai_suggested_post_text: string | null;
  ai_suggested_hashtags: string | null;
  ai_category: string | null;
  ai_platform_suggestion: string | null;
  ai_last_analyzed_at: string | null;
  posted_at: string | null;
  archived_at: string | null;
  storage_status: 'local' | 'cloud' | 'missing' | 'unknown';
  quick_summary: string | null;
  quick_category: string | null;
  quick_tags: string | null;
  quick_summary_source: string | null;
  quick_summary_model: string | null;
  quick_summary_at: string | null;
  ai_quality_notes: string | null;
}

export type LibraryItem = Pick<Reel, 'id' | 'filename' | 'filepath' | 'file_size' | 'storage_provider' | 'content_hash' | 'status' | 'storage_status'>;

export interface StatusCounts {
  all: number;
  draft: number;
  needs_review: number;
  ready: number;
  posted: number;
  archived: number;
}

export interface HealthStatus {
  status: string;
  gemini_configured: boolean;
  gemini_model: string;
  reels_folder_configured: boolean;
  reels_folder_path: string;
  db_path: string;
  thumbnails_folder_path: string;
}

export interface ScanResult {
  status: string;
  scanned_count: number;
  added_count: number;
  updated_count: number;
  missing_count: number;
  skipped_count: number;
  moved_count: number;
}

export interface ThumbnailBackfillResult {
  processed: number;
  generated: number;
  failed: number;
  remaining: number;
}

export interface ArchiveStatus {
  storage_provider: 'local' | 'dropbox';
  scan: { running?: boolean; finished_at?: string; error?: string; added?: number; scanned?: number; skipped?: number };
  scan_interval_seconds: number;
  auto_scan: boolean;
  auto_quick_summary: boolean;
  quick_model: string;
  paused: boolean;
  blocked_reason: string | null;
  jobs: Record<string, number>;
  storage: Record<string, number>;
  described: number;
  recent_jobs: { reel_id: number; filename: string; status: string; error: string | null }[];
  usage: { requests: number; input_tokens: number; output_tokens: number; estimated_cost_usd: number;
    quick_today_usd: number; quick_daily_budget_usd: number; quick_estimate_per_reel_usd: number | null; unpriced_requests: number };
}

// Global fetch helper with error handling
export async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options?.headers || {}),
    },
  });
  
  if (!response.ok) {
    if (response.status === 401) window.dispatchEvent(new Event('reelvault-session-expired'));
    let message = `API request failed with status ${response.status}`;
    try {
      const errorData = await response.json();
      message = typeof errorData.detail === 'string' ? errorData.detail : message;
    } catch {
      // ignore
    }
    throw new Error(message);
  }
  
  return response.json() as Promise<T>;
}

export interface Job<T = unknown> {
  id: string; kind: string; reel_id: number | null;
  status: 'queued' | 'running' | 'succeeded' | 'failed';
  result: T; error: string | null;
}

export interface PreviewInfo {
  status: 'not_generated' | 'queued' | 'running' | 'ready' | 'failed' | 'evicted' | 'unavailable';
  key: string; bytes: number; duration_seconds: number; url: string | null; error: string | null;
}

export interface PreviewStorage {
  jobs: Record<string, number>; bytes: number; reserved_bytes: number; budget_bytes: number;
  auto_enabled: boolean; paused: boolean; blocked_reason: string | null; delay_seconds: number;
}

async function submitJob<T>(path: string): Promise<T> {
  let job = await apiFetch<Job<T>>(path, { method: 'POST' });
  const deadline = Date.now() + 15 * 60 * 1000;
  while (job.status === 'queued' || job.status === 'running') {
    if (Date.now() > deadline) throw new Error(`Job ${job.id} is still running. Check Settings for its result.`);
    await new Promise(resolve => setTimeout(resolve, 1000));
    job = await apiFetch<Job<T>>(`/api/v1/jobs/${job.id}`);
  }
  if (job.status === 'failed') throw new Error(job.error || 'Background job failed.');
  return job.result;
}

export const api = {
  getLibraryIndex: () => apiFetch<LibraryItem[]>('/api/reels/library'),
  getArchiveStatus: () => apiFetch<ArchiveStatus>('/api/archive'),
  describeMissing: (reelIds?: number[], retry = false) => apiFetch<{ queued: number }>('/api/archive/describe', {
    method: 'POST', body: JSON.stringify({ reel_ids: reelIds, retry }),
  }),
  pauseDescriptions: (paused: boolean) => apiFetch('/api/archive/pause', { method: 'POST', body: JSON.stringify({ paused }) }),
  getHealth: () => apiFetch<HealthStatus>('/api/health'),
  
  getReels: (params?: {
    status?: string;
    approved?: boolean;
    search?: string;
    has_final_post?: boolean;
    has_ai_summary?: boolean;
    has_quick_summary?: boolean;
    availability?: string;
  }) => {
    const query = new URLSearchParams();
    if (params) {
      if (params.availability) query.append('availability', params.availability);
      if (params.has_quick_summary !== undefined) query.append('has_quick_summary', String(params.has_quick_summary));
      if (params.status) query.append('status', params.status);
      if (params.approved !== undefined) query.append('approved', String(params.approved));
      if (params.search) query.append('search', params.search);
      if (params.has_final_post !== undefined) query.append('has_final_post', String(params.has_final_post));
      if (params.has_ai_summary !== undefined) query.append('has_ai_summary', String(params.has_ai_summary));
    }
    const queryString = query.toString();
    return apiFetch<Reel[]>(`/api/reels${queryString ? '?' + queryString : ''}`);
  },
  
  getReel: (id: number) => apiFetch<Reel>(`/api/reels/${id}`),
  
  updateReel: (id: number, data: Partial<Reel>) => 
    apiFetch<Reel>(`/api/reels/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
    
  scanFolder: async (): Promise<ScanResult> => {
    const result = await submitJob<{ scanned: number; added: number; updated: number; moved?: number; missing: number; skipped: number }>('/api/v1/storage/refresh');
    return { status: 'success', scanned_count: result.scanned, added_count: result.added, updated_count: result.updated,
      missing_count: result.missing, skipped_count: result.skipped, moved_count: result.moved ?? 0 };
  },

  backfillThumbnails: (limit = 15) =>
    apiFetch<ThumbnailBackfillResult>(`/api/reels/thumbnails/backfill?limit=${limit}`, { method: 'POST' }),

  generateThumbnail: (id: number) =>
    submitJob<Reel>(`/api/v1/reels/${id}/thumbnail`),
  
  getStats: () => apiFetch<StatusCounts>('/api/reels/stats'),
  
  analyzeReel: (id: number) => submitJob<Reel>(`/api/v1/reels/${id}/analyze`),
  
  useAiCaption: (id: number) => apiFetch<Reel>(`/api/reels/${id}/use-ai-caption`, { method: 'POST' }),
  
  useAiHashtags: (id: number) => apiFetch<Reel>(`/api/reels/${id}/use-ai-hashtags`, { method: 'POST' }),
  
  markReady: (id: number) => apiFetch<Reel>(`/api/reels/${id}/mark-ready`, { method: 'POST' }),
  
  markPosted: (id: number) => apiFetch<Reel>(`/api/reels/${id}/mark-posted`, { method: 'POST' }),
  
  archiveReel: (id: number) => apiFetch<Reel>(`/api/reels/${id}/archive`, { method: 'POST' })
};
