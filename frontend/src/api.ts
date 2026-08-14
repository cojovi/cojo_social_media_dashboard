export interface Reel {
  id: number;
  filename: string;
  filepath: string;
  file_extension: string;
  file_size: number;
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
}

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
}

export interface ThumbnailBackfillResult {
  processed: number;
  generated: number;
  failed: number;
  remaining: number;
}

// Global fetch helper with error handling
async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options?.headers || {}),
    },
  });
  
  if (!response.ok) {
    let message = `API request failed with status ${response.status}`;
    try {
      const errorData = await response.json();
      message = errorData.detail || message;
    } catch {
      // ignore
    }
    throw new Error(message);
  }
  
  return response.json() as Promise<T>;
}

export const api = {
  getHealth: () => apiFetch<HealthStatus>('/api/health'),
  
  getReels: (params?: {
    status?: string;
    approved?: boolean;
    search?: string;
    has_final_post?: boolean;
    has_ai_summary?: boolean;
  }) => {
    const query = new URLSearchParams();
    if (params) {
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
    
  scanFolder: () => apiFetch<ScanResult>('/api/reels/scan', { method: 'POST' }),

  backfillThumbnails: (limit = 15) =>
    apiFetch<ThumbnailBackfillResult>(`/api/reels/thumbnails/backfill?limit=${limit}`, { method: 'POST' }),

  generateThumbnail: (id: number) =>
    apiFetch<Reel>(`/api/reels/${id}/thumbnail`, { method: 'POST' }),
  
  getStats: () => apiFetch<StatusCounts>('/api/reels/stats'),
  
  analyzeReel: (id: number) => apiFetch<Reel>(`/api/reels/${id}/analyze`, { method: 'POST' }),
  
  useAiCaption: (id: number) => apiFetch<Reel>(`/api/reels/${id}/use-ai-caption`, { method: 'POST' }),
  
  useAiHashtags: (id: number) => apiFetch<Reel>(`/api/reels/${id}/use-ai-hashtags`, { method: 'POST' }),
  
  markReady: (id: number) => apiFetch<Reel>(`/api/reels/${id}/mark-ready`, { method: 'POST' }),
  
  markPosted: (id: number) => apiFetch<Reel>(`/api/reels/${id}/mark-posted`, { method: 'POST' }),
  
  archiveReel: (id: number) => apiFetch<Reel>(`/api/reels/${id}/archive`, { method: 'POST' })
};
