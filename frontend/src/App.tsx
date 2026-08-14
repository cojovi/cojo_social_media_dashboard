import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { 
  Film, CheckCircle2, AlertCircle, FileText, Send, Archive, 
  Settings as SettingsIcon, Search, RefreshCw, Sparkles, 
  Copy, Trash2, Video, Info, Folder, ChevronRight, ChevronDown, StickyNote, ScanEye, X,
  CheckSquare, Square, ListChecks, Loader2
} from 'lucide-react';
import { api } from './api';
import type { Reel, StatusCounts, HealthStatus } from './api';
import { useAnalysisQueue } from './useAnalysisQueue';
import {
  buildFolderTree,
  filterReelsByFolder,
  countReelsInFolder,
  getRelativeFolder,
  type FolderNode,
} from './folders';

export default function App() {
  const [activeTab, setActiveTab] = useState<'all' | 'draft' | 'needs_review' | 'ready' | 'posted' | 'archived' | 'settings'>('all');
  const [reels, setReels] = useState<Reel[]>([]);
  const [stats, setStats] = useState<StatusCounts | null>(null);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [editingReel, setEditingReel] = useState<Reel | null>(null);
  const [hoveredCardId, setHoveredCardId] = useState<number | null>(null);
  const [selectedFolder, setSelectedFolder] = useState<string | null>(null);
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set());
  const [quickLookReel, setQuickLookReel] = useState<Reel | null>(null);
  const [thumbBackfillRunning, setThumbBackfillRunning] = useState(false);
  const thumbBackfillStartedRef = useRef(false);
  
  // Filters
  const [searchTerm, setSearchTerm] = useState('');
  const [hasFinalPost, setHasFinalPost] = useState<boolean | null>(null);
  const [hasAiSummary, setHasAiSummary] = useState<boolean | null>(null);
  
  // Toasts
  const [toasts, setToasts] = useState<{ id: number; message: string; type: 'success' | 'error' | 'warning' }[]>([]);
  
  // Form States (for the currently edited reel)
  const [statusInput, setStatusInput] = useState<string>('draft');
  const [approvedInput, setApprovedInput] = useState<boolean>(false);
  const [manualPostInput, setManualPostInput] = useState<string>('');
  const [finalPostInput, setFinalPostInput] = useState<string>('');
  const [hashtagsInput, setHashtagsInput] = useState<string>('');
  const [notesInput, setNotesInput] = useState<string>('');
  const [saveStatus, setSaveStatus] = useState<'idle' | 'pending' | 'saving' | 'saved' | 'error'>('idle');
  const [saving, setSaving] = useState(false);

  const saveBaselineRef = useRef<Reel | null>(null);
  const editingIdRef = useRef<number | null>(null);
  const autosaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const savingLockRef = useRef(false);

  const addToast = useCallback((message: string, type: 'success' | 'error' | 'warning' = 'success') => {
    const id = Date.now();
    setToasts(prev => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, 5000);
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      // Load stats
      const counts = await api.getStats();
      setStats(counts);

      // Load health
      const status = await api.getHealth();
      setHealth(status);

      // Load reels list matching active tab filter
      const filterParams: any = {
        search: searchTerm || undefined,
        has_final_post: hasFinalPost !== null ? hasFinalPost : undefined,
        has_ai_summary: hasAiSummary !== null ? hasAiSummary : undefined,
      };
      
      if (activeTab !== 'all' && activeTab !== 'settings') {
        filterParams.status = activeTab;
      }
      
      const list = await api.getReels(filterParams);
      setReels(list);
    } catch (error: any) {
      addToast(error.message || "Failed to load database content.", "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab !== 'settings') {
      loadData();
    } else {
      api.getHealth().then(setHealth).catch(() => {});
    }
  }, [activeTab, searchTerm, hasFinalPost, hasAiSummary]);

  useEffect(() => {
    if (activeTab !== 'all') {
      setSelectedFolder(null);
    }
    setSelectionMode(false);
    setSelectedIds(new Set());
  }, [activeTab]);

  const reelsRoot = health?.reels_folder_path || '';
  const folderTree = useMemo(
    () => (reelsRoot ? buildFolderTree(reels, reelsRoot) : []),
    [reels, reelsRoot]
  );
  const displayedReels = useMemo(
    () => (activeTab === 'all' && reelsRoot ? filterReelsByFolder(reels, reelsRoot, selectedFolder) : reels),
    [reels, reelsRoot, selectedFolder, activeTab]
  );

  const syncFormFromReel = (reel: Reel) => {
    setStatusInput(reel.status);
    setApprovedInput(reel.approved);
    setManualPostInput(reel.manual_post_text || '');
    setFinalPostInput(reel.final_post_text || '');
    setHashtagsInput(reel.hashtags || '');
    setNotesInput(reel.notes || '');
  };

  const handleReelUpdatedFromQueue = useCallback((updated: Reel) => {
    setReels(prev => prev.map(r => (r.id === updated.id ? updated : r)));
    setEditingReel(current => {
      if (current?.id === updated.id) {
        saveBaselineRef.current = updated;
        syncFormFromReel(updated);
        return updated;
      }
      return current;
    });
  }, []);

  const {
    queue: analysisQueue,
    activeId: analyzingId,
    queuedCount,
    isProcessing: analysisProcessing,
    enqueue: enqueueAnalysis,
    clearCompleted: clearAnalysisQueue,
  } = useAnalysisQueue({
    geminiConfigured: Boolean(health?.gemini_configured),
    onReelUpdated: handleReelUpdatedFromQueue,
    onToast: addToast,
  });

  const toggleReelSelection = (id: number) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectAllVisible = () => {
    setSelectedIds(new Set(displayedReels.map(r => r.id)));
  };

  const clearSelection = () => setSelectedIds(new Set());

  const handleBatchAnalyze = () => {
    const selected = reels.filter(r => selectedIds.has(r.id));
    if (selected.length === 0) return;
    enqueueAnalysis(selected);
    setSelectedIds(new Set());
    setSelectionMode(false);
  };

  const getReelQueueStatus = (id: number) => analysisQueue.find(item => item.id === id)?.status;

  const formDiffersFromBaseline = useCallback((
    baseline: Reel | null,
    fields: {
      status: string;
      approved: boolean;
      manual: string;
      final: string;
      hashtags: string;
      notes: string;
    }
  ) => {
    if (!baseline) return false;
    return (
      fields.status !== baseline.status ||
      fields.approved !== baseline.approved ||
      fields.manual !== (baseline.manual_post_text || '') ||
      fields.final !== (baseline.final_post_text || '') ||
      fields.hashtags !== (baseline.hashtags || '') ||
      fields.notes !== (baseline.notes || '')
    );
  }, []);

  const persistReel = useCallback(async (options?: { silent?: boolean; reelId?: number }) => {
    const silent = options?.silent ?? false;
    const reelId = options?.reelId ?? editingReel?.id;
    if (!reelId || savingLockRef.current) return false;

    const payload = {
      status: statusInput as Reel['status'],
      approved: approvedInput,
      manual_post_text: manualPostInput,
      final_post_text: finalPostInput,
      hashtags: hashtagsInput,
      notes: notesInput,
    };

    if (!formDiffersFromBaseline(saveBaselineRef.current, {
      status: payload.status,
      approved: payload.approved,
      manual: payload.manual_post_text,
      final: payload.final_post_text ?? '',
      hashtags: payload.hashtags ?? '',
      notes: payload.notes ?? '',
    })) {
      return true;
    }

    savingLockRef.current = true;
    setSaving(true);
    setSaveStatus('saving');
    try {
      const updated = await api.updateReel(reelId, payload);
      if (editingIdRef.current === reelId) {
        saveBaselineRef.current = updated;
        setEditingReel(updated);
        syncFormFromReel(updated);
      }
      setReels(prev => prev.map(r => (r.id === updated.id ? updated : r)));
      api.getStats().then(setStats).catch(() => {});
      setSaveStatus('saved');
      if (!silent) addToast('Draft saved to database.', 'success');
      return true;
    } catch (error: any) {
      setSaveStatus('error');
      addToast(error.message || 'Failed to save reel details.', 'error');
      return false;
    } finally {
      savingLockRef.current = false;
      setSaving(false);
    }
  }, [
    editingReel?.id,
    statusInput,
    approvedInput,
    manualPostInput,
    finalPostInput,
    hashtagsInput,
    notesInput,
    formDiffersFromBaseline,
  ]);

  useEffect(() => {
    if (!editingReel || !saveBaselineRef.current) return;

    const dirty = formDiffersFromBaseline(saveBaselineRef.current, {
      status: statusInput,
      approved: approvedInput,
      manual: manualPostInput,
      final: finalPostInput,
      hashtags: hashtagsInput,
      notes: notesInput,
    });

    if (!dirty) {
      setSaveStatus('saved');
      return;
    }

    setSaveStatus('pending');
    if (autosaveTimerRef.current) clearTimeout(autosaveTimerRef.current);
    autosaveTimerRef.current = setTimeout(() => {
      void persistReel({ silent: true });
    }, 600);

    return () => {
      if (autosaveTimerRef.current) clearTimeout(autosaveTimerRef.current);
    };
  }, [
    editingReel?.id,
    statusInput,
    approvedInput,
    manualPostInput,
    finalPostInput,
    hashtagsInput,
    notesInput,
    formDiffersFromBaseline,
    persistReel,
  ]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 's') {
        e.preventDefault();
        if (editingReel) void persistReel();
      }
      if (e.key === 'Escape' && quickLookReel) {
        setQuickLookReel(null);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [editingReel, persistReel, quickLookReel]);

  useEffect(() => {
    if (loading || activeTab === 'settings' || thumbBackfillStartedRef.current) return;
    const missing = reels.filter(r => !r.thumbnail_path).length;
    if (missing === 0) return;

    thumbBackfillStartedRef.current = true;
    let cancelled = false;

    const runBackfill = async () => {
      setThumbBackfillRunning(true);
      try {
        while (!cancelled) {
          const result = await api.backfillThumbnails(12);
          if (result.generated > 0) {
            const filterParams: Parameters<typeof api.getReels>[0] = {
              search: searchTerm || undefined,
              has_final_post: hasFinalPost !== null ? hasFinalPost : undefined,
              has_ai_summary: hasAiSummary !== null ? hasAiSummary : undefined,
            };
            if (activeTab !== 'all') {
              filterParams.status = activeTab;
            }
            const list = await api.getReels(filterParams);
            if (!cancelled) setReels(list);
          }
          if (result.remaining <= 0 || result.generated === 0) break;
          await new Promise(r => setTimeout(r, 400));
        }
      } catch {
        // silent — user can rescan manually
      } finally {
        if (!cancelled) setThumbBackfillRunning(false);
      }
    };

    void runBackfill();
    return () => { cancelled = true; };
  }, [loading, activeTab, reels.length]);

  const getCaptionPreview = (reel: Reel) => {
    if (reel.final_post_text?.trim()) return reel.final_post_text;
    if (reel.manual_post_text?.trim()) return reel.manual_post_text;
    if (reel.notes?.trim()) return `[Note] ${reel.notes}`;
    return 'No draft saved yet. Open workbench to add caption, hashtags, or notes.';
  };

  const toggleFolderExpanded = (path: string) => {
    setExpandedFolders(prev => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const handleQuickLook = (reel: Reel) => {
    setQuickLookReel(reel);
    if (!reel.thumbnail_path) {
      void api.generateThumbnail(reel.id).then(updated => {
        setReels(prev => prev.map(r => (r.id === updated.id ? updated : r)));
      }).catch(() => {});
    }
  };

  const handleScan = async () => {
    setScanning(true);
    addToast("Scanning local folder for new video assets...", "warning");
    try {
      const result = await api.scanFolder();
      addToast(
        `Directory scan completed! Scanned: ${result.scanned_count}, Added: ${result.added_count}, Updated: ${result.updated_count}`,
        "success"
      );
      loadData();
    } catch (error: any) {
      addToast(error.message || "Failed to scan folder.", "error");
    } finally {
      setScanning(false);
    }
  };

  const handleCloseWorkbench = async () => {
    if (autosaveTimerRef.current) {
      clearTimeout(autosaveTimerRef.current);
      autosaveTimerRef.current = null;
    }
    if (editingReel) {
      await persistReel({ silent: true, reelId: editingReel.id });
    }
    editingIdRef.current = null;
    saveBaselineRef.current = null;
    setEditingReel(null);
    setSaveStatus('idle');
  };

  const handleSelectReel = async (reel: Reel) => {
    if (editingReel?.id === reel.id) return;

    if (editingReel && editingReel.id !== reel.id) {
      if (autosaveTimerRef.current) clearTimeout(autosaveTimerRef.current);
      await persistReel({ silent: true, reelId: editingReel.id });
    }

    editingIdRef.current = reel.id;
    setEditingReel(reel);
    syncFormFromReel(reel);
    saveBaselineRef.current = reel;
    setSaveStatus('saved');

    try {
      const fresh = await api.getReel(reel.id);
      if (editingIdRef.current !== reel.id) return;
      saveBaselineRef.current = fresh;
      setEditingReel(fresh);
      syncFormFromReel(fresh);
      setReels(prev => prev.map(r => (r.id === fresh.id ? fresh : r)));
    } catch {
      addToast('Could not refresh reel from server.', 'warning');
    }
  };

  const handleSaveReel = async () => {
    if (autosaveTimerRef.current) clearTimeout(autosaveTimerRef.current);
    await persistReel();
  };

  const handleAnalyze = (id: number) => {
    const reel = reels.find(r => r.id === id);
    if (reel) enqueueAnalysis([reel]);
  };

  const handleUseAiCaption = async () => {
    if (!editingReel) return;
    try {
      const updated = await api.useAiCaption(editingReel.id);
      setEditingReel(updated);
      setFinalPostInput(updated.final_post_text || '');
      addToast("Copied Gemini suggestion into final post caption.", "success");
    } catch (error: any) {
      addToast(error.message, "error");
    }
  };

  const handleUseAiHashtags = async () => {
    if (!editingReel) return;
    try {
      const updated = await api.useAiHashtags(editingReel.id);
      setEditingReel(updated);
      setHashtagsInput(updated.hashtags || '');
      addToast("Copied Gemini suggested tags to active list.", "success");
    } catch (error: any) {
      addToast(error.message, "error");
    }
  };

  const handleMarkReady = async (id: number) => {
    try {
      const updated = await api.markReady(id);
      addToast("Reel approved and pushed to the Ready Queue!", "success");
      if (editingReel && editingReel.id === id) {
        setEditingReel(updated);
        setStatusInput(updated.status);
        setApprovedInput(updated.approved);
      }
      loadData();
    } catch (error: any) {
      addToast(error.message || "Ready verification failed. A final caption is required.", "error");
    }
  };

  const handleMarkPosted = async (id: number) => {
    try {
      const updated = await api.markPosted(id);
      addToast("Reel marked as posted on social media.", "success");
      if (editingReel && editingReel.id === id) {
        setEditingReel(updated);
        setStatusInput(updated.status);
      }
      loadData();
    } catch (error: any) {
      addToast(error.message, "error");
    }
  };

  const handleArchive = async (id: number) => {
    if (!window.confirm("Are you sure you want to archive this reel?")) return;
    try {
      const updated = await api.archiveReel(id);
      addToast("Reel sent to archives.", "success");
      if (editingReel && editingReel.id === id) {
        setEditingReel(updated);
        setStatusInput(updated.status);
      }
      loadData();
    } catch (error: any) {
      addToast(error.message, "error");
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    addToast("Copied to clipboard successfully!", "success");
  };

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const getStatusBadgeClass = (status: string) => {
    switch (status) {
      case 'ready': return 'bg-green-950/60 text-green-400 border border-green-700/60 shadow-[0_0_8px_rgba(34,197,94,0.2)]';
      case 'needs_review': return 'bg-amber-950/60 text-amber-400 border border-amber-700/60';
      case 'posted': return 'bg-blue-950/60 text-blue-400 border border-blue-700/60';
      case 'archived': return 'bg-zinc-950/60 text-zinc-400 border border-zinc-700/60';
      default: return 'bg-plum-800/80 text-purple-300 border border-purple-700/50';
    }
  };

  const renderFolderNode = (node: FolderNode, depth = 0) => {
    const hasChildren = node.children.length > 0;
    const isExpanded = expandedFolders.has(node.path);
    const isSelected = selectedFolder === node.path;
    const nestedCount = countReelsInFolder(reels, reelsRoot, node.path);

    return (
      <div key={node.path}>
        <button
          onClick={() => setSelectedFolder(node.path)}
          className={`w-full flex items-center gap-1.5 px-2 py-1.5 rounded-lg text-left text-xs transition-all cursor-pointer ${
            isSelected
              ? 'bg-neon-cyan/15 text-neon-cyan border border-neon-cyan/40'
              : 'text-purple-300 hover:bg-plum-900/60 hover:text-white border border-transparent'
          }`}
          style={{ paddingLeft: `${8 + depth * 14}px` }}
        >
          {hasChildren ? (
            <span
              onClick={(e) => { e.stopPropagation(); toggleFolderExpanded(node.path); }}
              className="shrink-0 p-0.5 rounded hover:bg-plum-800"
            >
              {isExpanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
            </span>
          ) : (
            <span className="w-4 shrink-0" />
          )}
          <Folder className="w-3.5 h-3.5 shrink-0 opacity-80" />
          <span className="truncate flex-1 font-medium">{node.name}</span>
          <span className="text-[10px] opacity-70 shrink-0">{nestedCount}</span>
        </button>
        {hasChildren && isExpanded && (
          <div>{node.children.map(child => renderFolderNode(child, depth + 1))}</div>
        )}
      </div>
    );
  };

  return (
    <div className="h-screen overflow-hidden bg-plum-950 flex font-sans select-none relative retro-scanlines">
      {/* Toast System */}
      <div className="fixed bottom-5 right-5 z-50 flex flex-col gap-3 max-w-sm">
        {toasts.map(t => (
          <div 
            key={t.id} 
            className={`p-4 rounded-lg backdrop-blur-md border shadow-lg flex items-start gap-3 transition-all duration-300 transform translate-y-0 ${
              t.type === 'error' ? 'bg-red-950/80 text-red-300 border-red-500/50 shadow-[0_0_10px_rgba(239,68,68,0.2)]' :
              t.type === 'warning' ? 'bg-amber-950/80 text-amber-300 border-amber-500/50' :
              'bg-cyan-950/80 text-cyan-300 border-cyan-500/50 shadow-[0_0_10px_rgba(6,182,212,0.2)]'
            }`}
          >
            {t.type === 'error' ? <AlertCircle className="w-5 h-5 shrink-0 mt-0.5" /> : <Info className="w-5 h-5 shrink-0 mt-0.5" />}
            <div>
              <p className="text-sm font-semibold">{t.type.toUpperCase()}</p>
              <p className="text-xs opacity-90">{t.message}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Left Sidebar Navigation */}
      <aside className="w-64 border-r border-plum-800 bg-plum-950/90 flex flex-col shrink-0">
        {/* Brand Logo */}
        <div className="h-20 flex items-center gap-3 px-6 border-b border-plum-800">
          <Film className="w-8 h-8 text-neon-cyan animate-pulse" />
          <div>
            <h1 className="text-xl font-retro font-bold tracking-widest text-transparent bg-clip-text bg-gradient-to-r from-neon-cyan to-neon-pink text-retro-glow">
              REELVAULT
            </h1>
            <p className="text-[9px] font-pixel text-neon-pink/80 tracking-tighter">LOCAL QUEUE</p>
          </div>
        </div>

        {/* Tab Items */}
        <nav className="flex-1 px-4 py-6 flex flex-col gap-2">
          {[
            { id: 'all', label: 'All Reels', icon: Film },
            { id: 'draft', label: 'Drafts', icon: FileText },
            { id: 'needs_review', label: 'Needs Review', icon: AlertCircle },
            { id: 'ready', label: 'Ready Queue', icon: CheckCircle2, highlight: true },
            { id: 'posted', label: 'Posted', icon: Send },
            { id: 'archived', label: 'Archived', icon: Archive },
          ].map(tab => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={async () => { await handleCloseWorkbench(); setActiveTab(tab.id as any); }}
                className={`w-full flex items-center justify-between px-4 py-3 rounded-lg border transition-all duration-200 cursor-pointer ${
                  isActive 
                    ? tab.highlight 
                      ? 'bg-gradient-to-r from-green-950 to-plum-900 border-green-500/80 text-green-400 shadow-[0_0_12px_rgba(34,197,94,0.3)]'
                      : 'bg-gradient-to-r from-purple-950 to-plum-900 border-neon-cyan/80 text-neon-cyan shadow-[0_0_12px_rgba(0,240,255,0.3)]'
                    : 'bg-transparent border-transparent text-purple-300/80 hover:bg-plum-900/40 hover:text-white'
                }`}
              >
                <div className="flex items-center gap-3">
                  <Icon className={`w-5 h-5 ${isActive ? 'text-cyan-400' : 'text-purple-400/80'}`} />
                  <span className="font-medium text-sm">{tab.label}</span>
                </div>
                {stats && stats[tab.id as keyof StatusCounts] !== undefined && (
                  <span className={`text-xs px-2 py-0.5 rounded-full font-bold ${
                    isActive ? 'bg-plum-950 text-white' : 'bg-plum-900 text-purple-400'
                  }`}>
                    {stats[tab.id as keyof StatusCounts]}
                  </span>
                )}
              </button>
            );
          })}
        </nav>

        {/* System Health Summary & Settings link */}
        <div className="p-4 border-t border-plum-800 bg-plum-950/50 flex flex-col gap-3">
          <button 
            onClick={async () => { await handleCloseWorkbench(); setActiveTab('settings'); }}
            className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-lg border text-sm transition-all duration-200 cursor-pointer ${
              activeTab === 'settings' 
                ? 'bg-plum-900 border-neon-pink/80 text-neon-pink shadow-[0_0_10px_rgba(255,0,127,0.3)]'
                : 'bg-transparent border-transparent text-purple-300 hover:bg-plum-900/40'
            }`}
          >
            <SettingsIcon className="w-4 h-4" />
            <span>Settings</span>
          </button>
          
          <div className="flex items-center justify-between px-2 text-[10px] text-purple-400/80">
            <span className="flex items-center gap-1.5">
              <span className={`w-2.5 h-2.5 rounded-full ${health?.gemini_configured ? 'bg-green-500 shadow-[0_0_6px_#22c55e]' : 'bg-red-500'}`} />
              AI: {health?.gemini_configured ? 'GEMINI ON' : 'OFFLINE'}
            </span>
            <span className="opacity-80">v1.0.0</span>
          </div>
        </div>
      </aside>

      {/* Main Command Workspace */}
      <main className="flex-1 flex flex-col min-w-0 bg-plum-900/20 overflow-hidden">
        {/* Top App Bar */}
        <header className="h-20 border-b border-plum-800 px-8 flex items-center justify-between shrink-0 glass-panel">
          <div className="flex items-center gap-3">
            <h2 className="text-xl font-retro font-semibold tracking-wider text-white">
              {activeTab === 'settings' ? 'SETTINGS CONTROL' : `${activeTab.replace('_', ' ').toUpperCase()} ARCHIVE`}
            </h2>
            {activeTab !== 'settings' && displayedReels.length > 0 && (
              <span className="text-xs px-2.5 py-0.5 rounded-full bg-plum-800 text-purple-300 font-bold border border-plum-700">
                {displayedReels.length} Reels
                {activeTab === 'all' && selectedFolder !== null && (
                  <span className="text-neon-cyan ml-1">
                    · {selectedFolder === '' ? 'Root' : selectedFolder}
                  </span>
                )}
              </span>
            )}
          </div>
          
          <div className="flex items-center gap-3">
            {activeTab !== 'settings' && health?.gemini_configured && (
              <button
                type="button"
                onClick={() => {
                  setSelectionMode(prev => !prev);
                  if (selectionMode) clearSelection();
                }}
                className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-semibold border transition-all cursor-pointer ${
                  selectionMode
                    ? 'bg-neon-cyan/15 text-neon-cyan border-neon-cyan/50'
                    : 'bg-plum-950 text-purple-300 border-plum-700 hover:border-neon-cyan/40'
                }`}
              >
                <ListChecks className="w-4 h-4" />
                <span>{selectionMode ? 'Done Selecting' : 'Select Reels'}</span>
              </button>
            )}
            {activeTab !== 'settings' && (
              <button 
                type="button"
                onClick={handleScan}
                disabled={scanning || thumbBackfillRunning}
                className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-neon-pink to-neon-orange text-white rounded-lg text-sm font-semibold border border-neon-pink hover:opacity-90 active:scale-95 shadow-[0_0_10px_rgba(255,0,127,0.4)] disabled:opacity-50 transition-all cursor-pointer"
              >
                <RefreshCw className={`w-4 h-4 ${scanning || thumbBackfillRunning ? 'animate-spin' : ''}`} />
                <span>{thumbBackfillRunning ? 'Building Thumbs…' : 'Rescan Folder'}</span>
              </button>
            )}
          </div>
        </header>

        {/* Content Box */}
        <div className="flex-1 p-8 flex gap-8 overflow-hidden min-h-0">
          {activeTab === 'settings' ? (
            /* Settings View Page */
            <div className="w-full max-w-3xl flex flex-col gap-6 overflow-y-auto pr-2">
              <div className="glass-panel rounded-xl border border-plum-800 p-6 flex flex-col gap-6 shadow-xl">
                <div className="flex items-center gap-3 border-b border-plum-800 pb-4">
                  <SettingsIcon className="w-6 h-6 text-neon-pink" />
                  <h3 className="text-lg font-retro font-bold text-white">Environment Configurations</h3>
                </div>
                
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="flex flex-col gap-1">
                    <label className="text-xs text-purple-400 font-bold uppercase">SQLite Database Path</label>
                    <div className="p-3 bg-plum-950 rounded-lg text-sm select-all font-mono border border-plum-800 break-all">
                      {health?.db_path || './data/reelvault.db'}
                    </div>
                  </div>

                  <div className="flex flex-col gap-1">
                    <label className="text-xs text-purple-400 font-bold uppercase">Reels Folder Location</label>
                    <div className="p-3 bg-plum-950 rounded-lg text-sm select-all font-mono border border-plum-800 break-all">
                      {health?.reels_folder_path || './reels'}
                    </div>
                  </div>

                  <div className="flex flex-col gap-1">
                    <label className="text-xs text-purple-400 font-bold uppercase">Thumbnails Storage Path</label>
                    <div className="p-3 bg-plum-950 rounded-lg text-sm select-all font-mono border border-plum-800 break-all">
                      {health?.thumbnails_folder_path || './data/thumbnails'}
                    </div>
                  </div>

                  <div className="flex flex-col gap-1">
                    <label className="text-xs text-purple-400 font-bold uppercase">Gemini AI Model Configuration</label>
                    <div className="p-3 bg-plum-950 rounded-lg text-sm select-all font-mono border border-plum-800 break-all">
                      {health?.gemini_model || 'gemini-2.5-flash'}
                    </div>
                  </div>
                </div>

                <div className="border-t border-plum-800 pt-6 flex flex-col gap-4">
                  <h4 className="text-sm font-bold text-white uppercase tracking-wider">Gemini API Connection</h4>
                  
                  {health?.gemini_configured ? (
                    <div className="p-4 bg-green-950/30 border border-green-800/50 rounded-lg flex items-start gap-3">
                      <Sparkles className="w-5 h-5 text-green-400 shrink-0 mt-0.5 animate-pulse" />
                      <div>
                        <p className="text-green-400 text-sm font-semibold">Gemini Service is ACTIVE</p>
                        <p className="text-xs text-green-300/80 mt-0.5">Your API key is active. Click "Analyze" on any reel detail card to have the AI write suggestions and summarize events.</p>
                      </div>
                    </div>
                  ) : (
                    <div className="p-4 bg-amber-950/30 border border-amber-800/50 rounded-lg flex items-start gap-3">
                      <AlertCircle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
                      <div>
                        <p className="text-amber-400 text-sm font-semibold">Gemini is Running in OFFLINE mode</p>
                        <p className="text-xs text-amber-300/80 mt-0.5">No GEMINI_API_KEY was found in your local .env configuration. You can still prewrite social copy manually, catalog reels, and manage approvals. To activate AI features, add a valid key inside your .env file.</p>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          ) : (
            /* Main Reel List Explorer & Detail Panel Split */
            <div className="flex-1 flex gap-8 min-w-0 items-stretch h-full overflow-hidden">
              {/* Reels List Explorer */}
              <div className="flex-1 flex flex-col gap-6 min-w-0 h-full overflow-hidden">
                {/* Filters Row */}
                <div className="glass-panel p-4 rounded-xl border border-plum-800 flex flex-wrap gap-4 items-center justify-between shadow-md">
                  <div className="relative flex-1 min-w-[240px]">
                    <Search className="w-4 h-4 text-purple-400 absolute left-3 top-1/2 -translate-y-1/2" />
                    <input 
                      type="text"
                      placeholder="Search by filename, caption, hashtag, or notes..."
                      value={searchTerm}
                      onChange={e => setSearchTerm(e.target.value)}
                      className="w-full bg-plum-950 border border-plum-800 rounded-lg pl-10 pr-4 py-2 text-sm text-white focus:outline-none focus:border-neon-cyan/80 transition-all font-sans"
                    />
                  </div>
                  
                  <div className="flex items-center gap-4 flex-wrap">
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-purple-400 uppercase font-bold">Caption:</span>
                      <select 
                        value={hasFinalPost === null ? 'all' : String(hasFinalPost)}
                        onChange={e => setHasFinalPost(e.target.value === 'all' ? null : e.target.value === 'true')}
                        className="bg-plum-950 border border-plum-800 text-xs text-purple-200 rounded-lg p-2 focus:outline-none"
                      >
                        <option value="all">All Captions</option>
                        <option value="true">Prewritten Only</option>
                        <option value="false">Missing Only</option>
                      </select>
                    </div>

                    <div className="flex items-center gap-2">
                      <span className="text-xs text-purple-400 uppercase font-bold">AI Status:</span>
                      <select 
                        value={hasAiSummary === null ? 'all' : String(hasAiSummary)}
                        onChange={e => setHasAiSummary(e.target.value === 'all' ? null : e.target.value === 'true')}
                        className="bg-plum-950 border border-plum-800 text-xs text-purple-200 rounded-lg p-2 focus:outline-none"
                      >
                        <option value="all">All Reels</option>
                        <option value="true">Analyzed Only</option>
                        <option value="false">Not Analyzed</option>
                      </select>
                    </div>
                  </div>
                </div>

                {/* Scrollable Reels List Grid Container */}
                <div className="flex-1 flex gap-4 min-h-0 overflow-hidden">
                  {activeTab === 'all' && reelsRoot && (
                    <div className="w-56 shrink-0 glass-panel rounded-xl border border-plum-800 flex flex-col overflow-hidden shadow-md">
                      <div className="p-3 border-b border-plum-800 flex items-center gap-2">
                        <Folder className="w-4 h-4 text-neon-cyan" />
                        <span className="text-xs font-bold uppercase text-purple-300 tracking-wider">Folders</span>
                      </div>
                      <div className="flex-1 overflow-y-auto p-2 flex flex-col gap-0.5">
                        <button
                          onClick={() => setSelectedFolder(null)}
                          className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-left text-xs transition-all cursor-pointer ${
                            selectedFolder === null
                              ? 'bg-neon-cyan/15 text-neon-cyan border border-neon-cyan/40'
                              : 'text-purple-300 hover:bg-plum-900/60 hover:text-white border border-transparent'
                          }`}
                        >
                          <Film className="w-3.5 h-3.5 shrink-0" />
                          <span className="flex-1 font-medium">All Reels</span>
                          <span className="text-[10px] opacity-70">{reels.length}</span>
                        </button>
                        <button
                          onClick={() => setSelectedFolder('')}
                          className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-left text-xs transition-all cursor-pointer ${
                            selectedFolder === ''
                              ? 'bg-neon-cyan/15 text-neon-cyan border border-neon-cyan/40'
                              : 'text-purple-300 hover:bg-plum-900/60 hover:text-white border border-transparent'
                          }`}
                        >
                          <Folder className="w-3.5 h-3.5 shrink-0" />
                          <span className="flex-1 font-medium">Root (no folder)</span>
                          <span className="text-[10px] opacity-70">{countReelsInFolder(reels, reelsRoot, '')}</span>
                        </button>
                        {folderTree.map(node => renderFolderNode(node))}
                      </div>
                    </div>
                  )}

                  <div className="flex-1 overflow-y-auto pr-1 min-w-0">
                  {loading ? (
                    <div className="grid grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-6">
                      {[1, 2, 3, 4].map(n => (
                        <div key={n} className="glass-panel h-[500px] rounded-xl border border-plum-800/40 p-4 animate-pulse flex flex-col gap-4">
                          <div className="flex-1 bg-plum-850 rounded-lg animate-pulse" />
                          <div className="h-4 bg-plum-800 rounded w-3/4 animate-pulse" />
                          <div className="h-4 bg-plum-800 rounded w-1/2 animate-pulse" />
                        </div>
                      ))}
                    </div>
                  ) : displayedReels.length === 0 ? (
                    <div className="glass-panel rounded-xl border border-plum-850 p-12 text-center flex flex-col items-center justify-center gap-4 flex-1">
                      <Film className="w-12 h-12 text-purple-500/50" />
                      <div>
                        <p className="text-lg font-retro font-bold text-purple-300">Archive matches no records</p>
                        <p className="text-sm text-purple-400/80 mt-1 max-w-sm">No reels correspond to your filters. Click 'Rescan Folder' to import videos or clear your search term.</p>
                      </div>
                    </div>
                  ) : (
                    <div className="grid grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-6 pb-6">
                      {displayedReels.map(reel => {
                        const hasFinalCaption = reel.final_post_text && reel.final_post_text.trim();
                        const hasManualDraft = reel.manual_post_text && reel.manual_post_text.trim();
                        const hasNotes = reel.notes && reel.notes.trim();
                        const isEditing = editingReel?.id === reel.id;
                        const folderLabel = reelsRoot ? getRelativeFolder(reel.filepath, reelsRoot) : '';
                        
                        return (
                          <div 
                            key={reel.id} 
                            onClick={() => {
                              if (selectionMode) {
                                toggleReelSelection(reel.id);
                                return;
                              }
                              void handleSelectReel(reel);
                            }}
                            onMouseEnter={() => !selectionMode && setHoveredCardId(reel.id)}
                            onMouseLeave={() => setHoveredCardId(null)}
                            className={`glass-panel rounded-xl border cursor-pointer overflow-hidden transition-all duration-300 flex flex-col h-[500px] group shadow-md hover:-translate-y-1.5 ${
                              isEditing 
                                ? 'border-neon-cyan animate-pulse-cyan' 
                                : selectedIds.has(reel.id)
                                  ? 'border-neon-pink ring-2 ring-neon-pink/40'
                                  : 'border-plum-800 hover:border-neon-cyan/50 hover:shadow-[0_0_12px_rgba(0,240,255,0.15)]'
                            }`}
                          >
                            {/* Card Thumbnail / Header Preview */}
                            <div className="h-[340px] bg-plum-950 relative overflow-hidden flex items-center justify-center shrink-0 border-b border-plum-850">
                              {selectionMode && (
                                <button
                                  type="button"
                                  onClick={(e) => { e.stopPropagation(); toggleReelSelection(reel.id); }}
                                  className="absolute top-2 right-2 z-20 p-1.5 rounded-lg bg-black/70 border border-plum-700 text-neon-cyan hover:bg-neon-cyan/20 cursor-pointer"
                                  title={selectedIds.has(reel.id) ? 'Deselect' : 'Select for AI analysis'}
                                >
                                  {selectedIds.has(reel.id)
                                    ? <CheckSquare className="w-4 h-4" />
                                    : <Square className="w-4 h-4" />}
                                </button>
                              )}

                              {getReelQueueStatus(reel.id) === 'processing' && (
                                <span className="absolute top-2 left-2 z-20 px-2 py-0.5 rounded bg-neon-pink/90 text-[9px] font-bold uppercase text-white flex items-center gap-1">
                                  <Loader2 className="w-3 h-3 animate-spin" />
                                  AI
                                </span>
                              )}
                              {getReelQueueStatus(reel.id) === 'queued' && (
                                <span className="absolute top-2 left-2 z-20 px-2 py-0.5 rounded bg-purple-900/90 text-[9px] font-bold uppercase text-purple-200 border border-purple-600">
                                  Queued
                                </span>
                              )}
                              {/* Ambient Blurred Background */}
                              {reel.thumbnail_path && (
                                <div 
                                  className="absolute inset-0 bg-cover bg-center blur-xl opacity-35 scale-110"
                                  style={{ backgroundImage: `url(/thumbnails/${reel.thumbnail_path})` }}
                                />
                              )}
                              
                              {hoveredCardId === reel.id ? (
                                <video 
                                  src={`/api/reels/${reel.id}/video`}
                                  muted
                                  autoPlay
                                  loop
                                  playsInline
                                  className="h-full aspect-[9/16] object-contain relative z-10 shadow-lg"
                                />
                              ) : reel.thumbnail_path ? (
                                <img 
                                  src={`/thumbnails/${reel.thumbnail_path}`} 
                                  alt={reel.filename} 
                                  className="h-full aspect-[9/16] object-contain relative z-10 group-hover:scale-102 transition-all duration-500 shadow-lg"
                                />
                              ) : (
                                <div className="w-full h-full bg-gradient-to-tr from-plum-800 via-plum-900 to-plum-950 flex flex-col items-center justify-center gap-2 relative z-10">
                                  <Video className="w-10 h-10 text-purple-500/60" />
                                  <span className="text-[10px] text-purple-400 font-bold uppercase tracking-wider">No Thumbnail</span>
                                </div>
                              )}

                              {/* Duration Badge */}
                              <span className="absolute bottom-2 right-2 px-2 py-0.5 rounded bg-black/80 backdrop-blur-md text-[10px] font-mono font-bold text-white tracking-wider border border-white/10">
                                {Math.floor(reel.duration_seconds / 60)}:
                                {String(Math.floor(reel.duration_seconds % 60)).padStart(2, '0')}
                              </span>
                              
                              {/* Approved Star Indicator */}
                              {reel.approved && (
                                <span className="absolute top-2 left-2 px-2 py-0.5 rounded bg-yellow-950/80 backdrop-blur-md text-[9px] font-pixel font-bold text-yellow-400 border border-yellow-700/60 flex items-center gap-1 shadow-[0_0_6px_rgba(234,179,8,0.3)] animate-pulse">
                                  ★ APPR
                                </span>
                              )}
                            </div>

                            {/* Card Body */}
                            <div className="flex-1 p-4 flex flex-col min-h-0 justify-between">
                              <div className="flex flex-col gap-2 min-h-0">
                                <div className="flex items-start justify-between gap-2">
                                  <h4 className="text-sm font-bold text-white truncate break-all shrink-0 max-w-[140px]" title={reel.filename}>
                                    {reel.filename}
                                  </h4>
                                  <span className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded-full shrink-0 ${getStatusBadgeClass(reel.status)}`}>
                                    {reel.status.replace('_', ' ')}
                                  </span>
                                </div>

                                {folderLabel && (
                                  <p className="text-[10px] text-purple-400/90 truncate font-mono flex items-center gap-1" title={folderLabel}>
                                    <Folder className="w-3 h-3 shrink-0" />
                                    {folderLabel}
                                  </p>
                                )}

                                {/* Caption Excerpt */}
                                <p className={`text-xs line-clamp-2 break-words shrink-0 ${
                                  hasFinalCaption ? 'text-purple-200/80 italic' : hasManualDraft ? 'text-purple-200/90' : 'text-purple-400/70'
                                }`}>
                                  {getCaptionPreview(reel)}
                                </p>

                                {(hasManualDraft || hasNotes) && !hasFinalCaption && (
                                  <div className="flex gap-1.5 flex-wrap">
                                    {hasManualDraft && (
                                      <span className="text-[9px] px-1.5 py-0.5 rounded bg-purple-950/80 text-purple-300 border border-purple-700/50 uppercase font-bold">
                                        Draft
                                      </span>
                                    )}
                                    {hasNotes && (
                                      <span className="text-[9px] px-1.5 py-0.5 rounded bg-amber-950/80 text-amber-300 border border-amber-700/50 uppercase font-bold flex items-center gap-0.5">
                                        <StickyNote className="w-2.5 h-2.5" />
                                        Notes
                                      </span>
                                    )}
                                  </div>
                                )}
                              </div>

                              {/* Tags / Action row */}
                              <div className="flex flex-col gap-3 shrink-0 pt-3 border-t border-plum-850">
                                {reel.hashtags && (
                                  <p className="text-[10px] text-neon-cyan truncate font-mono">
                                    {reel.hashtags}
                                  </p>
                                )}
                                
                                <div className="flex items-center justify-between gap-2">
                                  <div className="flex gap-2">
                                    <button
                                      type="button"
                                      onClick={(e) => { e.stopPropagation(); handleQuickLook(reel); }}
                                      className="p-1.5 rounded-lg bg-plum-950 border border-plum-800 text-neon-cyan hover:text-white hover:bg-neon-cyan/20 hover:border-neon-cyan/50 transition-all cursor-pointer"
                                      title="Quick Look (full size + audio)"
                                    >
                                      <ScanEye className="w-3.5 h-3.5" />
                                    </button>
                                    {health?.gemini_configured && (
                                      <button 
                                        type="button"
                                        onClick={(e) => { e.stopPropagation(); handleAnalyze(reel.id); }}
                                        disabled={getReelQueueStatus(reel.id) === 'queued' || getReelQueueStatus(reel.id) === 'processing'}
                                        className="p-1.5 rounded-lg bg-plum-950 border border-plum-800 text-neon-pink hover:text-white hover:bg-neon-pink/20 hover:border-neon-pink/50 transition-all cursor-pointer disabled:opacity-40"
                                        title="Queue Gemini AI Analysis"
                                      >
                                        <Sparkles className={`w-3.5 h-3.5 ${analyzingId === reel.id ? 'animate-spin' : ''}`} />
                                      </button>
                                    )}
                                    
                                    {!reel.approved && hasFinalCaption && (
                                      <button 
                                        onClick={(e) => { e.stopPropagation(); handleMarkReady(reel.id); }}
                                        className="px-2 py-1 bg-green-950/60 hover:bg-green-900/60 text-green-400 border border-green-800/80 rounded-lg text-[10px] font-bold tracking-wider transition-all cursor-pointer uppercase flex items-center gap-1"
                                        title="Approve & Mark Ready"
                                      >
                                        <CheckCircle2 className="w-3 h-3" />
                                        <span>Ready</span>
                                      </button>
                                    )}
                                  </div>
                                  
                                  <span className="text-[10px] text-purple-400 font-mono">
                                    ID: {reel.id}
                                  </span>
                                </div>
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                  </div>
                </div>
              </div>

              {/* Side Detail / Edit Panel */}
              {editingReel && (
                <div className="w-[450px] shrink-0 glass-panel rounded-xl border border-neon-cyan shadow-[0_0_20px_rgba(0,240,255,0.15)] flex flex-col overflow-hidden h-full z-10 animate-fade-in">
                  {/* Panel Title Header */}
                  <div className="p-4 border-b border-plum-800 bg-plum-950/80 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Film className="w-4 h-4 text-neon-cyan" />
                      <span className="font-retro font-bold text-sm tracking-wider text-white">REEL WORK BENCH</span>
                      {saveStatus === 'pending' && (
                        <span className="text-[10px] text-amber-400 font-bold uppercase">Unsaved</span>
                      )}
                      {saveStatus === 'saving' && (
                        <span className="text-[10px] text-neon-cyan font-bold uppercase animate-pulse">Saving…</span>
                      )}
                      {saveStatus === 'saved' && (
                        <span className="text-[10px] text-green-400 font-bold uppercase">Saved</span>
                      )}
                      {saveStatus === 'error' && (
                        <span className="text-[10px] text-red-400 font-bold uppercase">Save failed</span>
                      )}
                    </div>
                    <button 
                      type="button"
                      onClick={() => void handleCloseWorkbench()}
                      className="text-purple-400 hover:text-white font-bold text-xs border border-purple-800 rounded px-2 py-0.5 bg-plum-900 cursor-pointer"
                    >
                      CLOSE
                    </button>
                  </div>

                  {/* Panel Body */}
                  <div className="flex-1 overflow-y-auto p-5 flex flex-col gap-5">
                    {/* Integrated HTML5 Stream Player */}
                    <div className="h-[480px] bg-black rounded-lg overflow-hidden border border-plum-800 relative group flex items-center justify-center shadow-inner">
                      {editingReel.thumbnail_path && (
                        <div 
                          className="absolute inset-0 bg-cover bg-center blur-2xl opacity-25 scale-110"
                          style={{ backgroundImage: `url(/thumbnails/${editingReel.thumbnail_path})` }}
                        />
                      )}
                      <video 
                        key={editingReel.id} 
                        src={`/api/reels/${editingReel.id}/video`}
                        controls 
                        className="h-full aspect-[9/16] object-contain relative z-10 shadow-2xl"
                        preload="metadata"
                      />
                    </div>

                    {/* Metadata Grid */}
                    <div className="p-3 bg-plum-950 border border-plum-850 rounded-lg text-xs flex flex-col gap-2 font-sans text-purple-300">
                      <p className="truncate"><strong className="text-white">Filename:</strong> {editingReel.filename}</p>
                      <p className="truncate"><strong className="text-white">Path:</strong> {editingReel.filepath}</p>
                      <div className="grid grid-cols-2 gap-2 mt-1 pt-2 border-t border-plum-850">
                        <p><strong>Duration:</strong> {editingReel.duration_seconds.toFixed(1)}s</p>
                        <p><strong>File Size:</strong> {formatBytes(editingReel.file_size)}</p>
                      </div>
                    </div>

                    {/* Editor Form fields */}
                    <div className="flex flex-col gap-4">
                      {/* Status and Approved Checkbox */}
                      <div className="flex gap-4 items-center justify-between">
                        <div className="flex flex-col gap-1 flex-1">
                          <label className="text-xs text-purple-400 font-bold uppercase">Workflow Status</label>
                          <select 
                            value={statusInput}
                            onChange={e => setStatusInput(e.target.value)}
                            className="bg-plum-950 border border-plum-800 text-sm text-white rounded-lg p-2.5 focus:outline-none focus:border-neon-cyan"
                          >
                            <option value="draft">Draft</option>
                            <option value="needs_review">Needs Review</option>
                            <option value="ready">Ready Queue</option>
                            <option value="posted">Posted</option>
                            <option value="archived">Archived</option>
                          </select>
                        </div>

                        <div className="flex flex-col gap-1 shrink-0 pt-5">
                          <label className="flex items-center gap-2 p-2 rounded-lg bg-plum-950 border border-plum-800 cursor-pointer">
                            <input 
                              type="checkbox"
                              checked={approvedInput}
                              onChange={e => setApprovedInput(e.target.checked)}
                              className="w-4 h-4 rounded text-neon-cyan focus:ring-transparent accent-cyan-400 cursor-pointer"
                            />
                            <span className="text-xs text-white font-bold uppercase">Approved</span>
                          </label>
                        </div>
                      </div>

                      {/* Manual Caption Input */}
                      <div className="flex flex-col gap-1">
                        <label className="text-xs text-purple-400 font-bold uppercase flex justify-between">
                          <span>Manual Prewritten Caption</span>
                          <span className="text-[9px] text-purple-500 font-normal normal-case">auto-saves</span>
                        </label>
                        <textarea 
                          rows={3}
                          value={manualPostInput}
                          onChange={e => setManualPostInput(e.target.value)}
                          placeholder="Prewrite your caption text manually..."
                          className="w-full bg-plum-950 border border-plum-800 rounded-lg p-3 text-sm text-white focus:outline-none focus:border-neon-cyan font-sans"
                        />
                      </div>

                      {/* Hashtags Input */}
                      <div className="flex flex-col gap-1">
                        <label className="text-xs text-purple-400 font-bold uppercase">Hashtags</label>
                        <input 
                          type="text"
                          value={hashtagsInput}
                          onChange={e => setHashtagsInput(e.target.value)}
                          placeholder="e.g. #roofing #homeimprovement"
                          className="w-full bg-plum-950 border border-plum-800 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-neon-cyan font-sans"
                        />
                      </div>

                      {/* Notes Input */}
                      <div className="flex flex-col gap-1">
                        <label className="text-xs text-purple-400 font-bold uppercase">Internal Notes</label>
                        <textarea 
                          rows={2}
                          value={notesInput}
                          onChange={e => setNotesInput(e.target.value)}
                          placeholder="Add team notes, scheduling slots, etc..."
                          className="w-full bg-plum-950 border border-plum-800 rounded-lg p-3 text-sm text-white focus:outline-none focus:border-neon-cyan font-sans"
                        />
                      </div>

                      {/* Gemini Assistant Panel (collapsible or styled box if data exists) */}
                      {editingReel.ai_summary ? (
                        <div className="p-4 bg-plum-950 border border-neon-pink/40 rounded-lg flex flex-col gap-3 shadow-[0_0_10px_rgba(255,0,127,0.08)]">
                          <div className="flex items-center justify-between border-b border-plum-850 pb-2">
                            <span className="flex items-center gap-1.5 text-neon-pink font-bold text-xs uppercase">
                              <Sparkles className="w-3.5 h-3.5" />
                              Gemini Copy Writer
                            </span>
                            <span className="text-[9px] text-purple-400 font-mono">
                              {editingReel.ai_category} | {editingReel.ai_platform_suggestion}
                            </span>
                          </div>

                          <div className="flex flex-col gap-1">
                            <span className="text-[10px] text-purple-400 font-bold uppercase">AI Video Summary</span>
                            <p className="text-xs text-purple-200/90 leading-relaxed font-sans">{editingReel.ai_summary}</p>
                          </div>

                          <div className="flex flex-col gap-1 bg-plum-900/30 p-2 border border-plum-850 rounded">
                            <span className="text-[10px] text-neon-pink font-bold uppercase">AI Caption Suggestion</span>
                            <p className="text-xs text-purple-100 leading-relaxed italic select-all font-sans whitespace-pre-wrap">{editingReel.ai_suggested_post_text}</p>
                          </div>

                          {editingReel.ai_suggested_hashtags && (
                            <div className="flex flex-col gap-1">
                              <span className="text-[10px] text-purple-400 font-bold uppercase">AI Hashtags</span>
                              <p className="text-xs text-neon-cyan select-all font-mono">{editingReel.ai_suggested_hashtags}</p>
                            </div>
                          )}

                          <div className="grid grid-cols-2 gap-2 mt-2 pt-2 border-t border-plum-850">
                            <button 
                              onClick={handleUseAiCaption}
                              className="px-2 py-1.5 bg-gradient-to-r from-neon-pink to-neon-purple text-white text-[10px] font-bold uppercase rounded border border-neon-pink hover:opacity-90 active:scale-95 transition-all cursor-pointer"
                            >
                              Use Caption
                            </button>
                            <button 
                              onClick={handleUseAiHashtags}
                              className="px-2 py-1.5 bg-plum-900 text-neon-cyan hover:text-white text-[10px] font-bold uppercase rounded border border-neon-cyan/40 hover:bg-neon-cyan/20 transition-all cursor-pointer"
                            >
                              Use Hashtags
                            </button>
                          </div>
                        </div>
                      ) : (
                        health?.gemini_configured && (
                          <button
                            onClick={() => handleAnalyze(editingReel.id)}
                            disabled={getReelQueueStatus(editingReel.id) === 'queued' || getReelQueueStatus(editingReel.id) === 'processing'}
                            className="w-full py-3 bg-gradient-to-r from-neon-pink to-neon-purple hover:opacity-95 text-white rounded-lg text-xs font-retro font-bold border border-neon-pink shadow-[0_0_12px_rgba(255,0,127,0.35)] flex items-center justify-center gap-2 tracking-widest cursor-pointer disabled:opacity-50"
                          >
                            <Sparkles className={`w-4 h-4 ${analyzingId === editingReel.id ? 'animate-spin' : ''}`} />
                            <span>{getReelQueueStatus(editingReel.id) === 'queued' ? 'QUEUED FOR ANALYSIS' : 'ANALYZE WITH GEMINI AI'}</span>
                          </button>
                        )
                      )}

                      {/* Final Copywriting Output Box */}
                      <div className="flex flex-col gap-1 pt-2 border-t border-plum-850">
                        <label className="text-xs text-green-400 font-bold uppercase flex items-center justify-between">
                          <span>Final Post Caption (Active Queue Text)</span>
                          <button 
                            onClick={() => copyToClipboard(finalPostInput)}
                            disabled={!finalPostInput}
                            className="text-[10px] text-neon-cyan hover:underline flex items-center gap-0.5 lowercase cursor-pointer disabled:opacity-50"
                          >
                            <Copy className="w-3 h-3" />
                            <span>copy</span>
                          </button>
                        </label>
                        <textarea 
                          rows={4}
                          value={finalPostInput}
                          onChange={e => setFinalPostInput(e.target.value)}
                          placeholder="This text will be read directly by automated posting agents once approved."
                          className="w-full bg-plum-950 border border-green-800/60 rounded-lg p-3 text-sm text-green-300 font-medium focus:outline-none focus:border-green-400 font-sans shadow-[0_0_8px_rgba(34,197,94,0.05)]"
                        />
                      </div>
                    </div>
                  </div>

                  {/* Panel Actions Bottom Bar */}
                  <div className="p-4 border-t border-plum-800 bg-plum-950/80 flex flex-wrap gap-2 shrink-0">
                    <button 
                      type="button"
                      onClick={() => void handleSaveReel()}
                      disabled={saving}
                      className="flex-1 px-3 py-2 bg-plum-900 border border-plum-700 text-white rounded-lg text-xs font-bold uppercase hover:bg-plum-850 hover:border-purple-500/50 cursor-pointer active:scale-95 transition-all text-center disabled:opacity-50"
                    >
                      {saving ? 'Saving…' : 'Save Now'}
                    </button>
                    
                    {!editingReel.approved && (
                      <button 
                        onClick={() => handleMarkReady(editingReel.id)}
                        className="px-3 py-2 bg-green-950 text-green-400 border border-green-700 rounded-lg text-xs font-bold uppercase hover:bg-green-900/40 hover:border-green-500 active:scale-95 cursor-pointer transition-all flex items-center gap-1.5"
                      >
                        <CheckCircle2 className="w-4 h-4" />
                        <span>Ready</span>
                      </button>
                    )}

                    {editingReel.status !== 'posted' && (
                      <button 
                        onClick={() => handleMarkPosted(editingReel.id)}
                        className="px-3 py-2 bg-blue-950 text-blue-400 border border-blue-700 rounded-lg text-xs font-bold uppercase hover:bg-blue-900/40 cursor-pointer active:scale-95 transition-all flex items-center gap-1.5"
                        title="Mark as Posted"
                      >
                        <Send className="w-4 h-4" />
                        <span>Posted</span>
                      </button>
                    )}

                    <button 
                      onClick={() => handleArchive(editingReel.id)}
                      className="p-2 bg-red-950/60 border border-red-900 text-red-400 hover:bg-red-900/40 rounded-lg cursor-pointer"
                      title="Archive Reel"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </main>

      {/* Multi-select batch action bar */}
      {selectionMode && activeTab !== 'settings' && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-[150] glass-panel border border-neon-pink/50 rounded-xl px-5 py-3 flex items-center gap-4 shadow-[0_0_24px_rgba(255,0,127,0.25)]">
          <span className="text-sm text-white font-semibold whitespace-nowrap">
            {selectedIds.size} selected
          </span>
          <button
            type="button"
            onClick={selectAllVisible}
            className="text-xs text-purple-300 hover:text-white underline cursor-pointer"
          >
            Select all visible ({displayedReels.length})
          </button>
          <button
            type="button"
            onClick={clearSelection}
            className="text-xs text-purple-300 hover:text-white underline cursor-pointer"
          >
            Clear
          </button>
          <button
            type="button"
            onClick={handleBatchAnalyze}
            disabled={selectedIds.size === 0 || !health?.gemini_configured}
            className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-neon-pink to-neon-purple text-white rounded-lg text-xs font-bold uppercase border border-neon-pink hover:opacity-90 disabled:opacity-40 cursor-pointer"
          >
            <Sparkles className="w-4 h-4" />
            Generate AI Analysis
          </button>
        </div>
      )}

      {/* AI analysis queue panel */}
      {analysisQueue.length > 0 && (
        <div className="fixed bottom-6 right-5 z-[150] w-80 glass-panel border border-plum-700 rounded-xl shadow-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-plum-800 flex items-center justify-between bg-plum-950/80">
            <div className="flex items-center gap-2">
              <Sparkles className={`w-4 h-4 text-neon-pink ${analysisProcessing ? 'animate-pulse' : ''}`} />
              <span className="text-xs font-bold uppercase text-white tracking-wider">AI Analysis Queue</span>
            </div>
            <button
              type="button"
              onClick={clearAnalysisQueue}
              className="text-[10px] text-purple-400 hover:text-white uppercase cursor-pointer"
            >
              Clear done
            </button>
          </div>
          <div className="max-h-52 overflow-y-auto p-2 flex flex-col gap-1">
            {analysisQueue.map(item => (
              <div
                key={`${item.id}-${item.status}`}
                className="flex items-center gap-2 px-2 py-1.5 rounded-lg text-xs bg-plum-950/60"
              >
                {item.status === 'processing' && <Loader2 className="w-3.5 h-3.5 text-neon-pink animate-spin shrink-0" />}
                {item.status === 'queued' && <span className="w-3.5 h-3.5 rounded-full border border-purple-500 shrink-0" />}
                {item.status === 'done' && <CheckCircle2 className="w-3.5 h-3.5 text-green-400 shrink-0" />}
                {item.status === 'failed' && <AlertCircle className="w-3.5 h-3.5 text-red-400 shrink-0" />}
                <span className="truncate flex-1 text-purple-200" title={item.filename}>{item.filename}</span>
                <span className="text-[9px] uppercase text-purple-500 shrink-0">{item.status}</span>
              </div>
            ))}
          </div>
          {analysisProcessing && (
            <div className="px-4 py-2 border-t border-plum-800 text-[10px] text-purple-400">
              Processing one reel at a time · {queuedCount} waiting
            </div>
          )}
        </div>
      )}

      {/* macOS-style Quick Look overlay */}
      {quickLookReel && (
        <div
          className="fixed inset-0 z-[200] bg-black/92 backdrop-blur-md flex flex-col items-center justify-center p-6 animate-fade-in"
          onClick={() => setQuickLookReel(null)}
        >
          <div
            className="relative flex flex-col items-center max-w-lg w-full gap-4"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="w-full flex items-center justify-between gap-4">
              <div className="min-w-0">
                <p className="text-xs text-neon-cyan font-bold uppercase tracking-widest">Quick Look</p>
                <p className="text-sm text-white font-semibold truncate" title={quickLookReel.filename}>
                  {quickLookReel.filename}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setQuickLookReel(null)}
                className="shrink-0 p-2 rounded-lg border border-plum-700 bg-plum-950 text-purple-300 hover:text-white hover:border-neon-cyan/50 cursor-pointer"
                title="Close (Esc)"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="w-full flex items-center justify-center rounded-xl overflow-hidden border border-plum-700 bg-black shadow-[0_0_40px_rgba(0,240,255,0.12)]">
              <video
                key={quickLookReel.id}
                src={`/api/reels/${quickLookReel.id}/video`}
                controls
                autoPlay
                playsInline
                className="max-h-[75vh] w-full aspect-[9/16] object-contain"
              />
            </div>

            <p className="text-[11px] text-purple-400 text-center">
              Space to play/pause · Esc to close · Audio enabled
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
