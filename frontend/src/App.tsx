import { useState, useEffect, useLayoutEffect, useMemo, useRef, useCallback } from 'react';
import { 
  Film, CheckCircle2, AlertCircle, FileText, Send, Archive, 
  Settings as SettingsIcon, Search, RefreshCw, Sparkles, 
  Copy, Trash2, Video, Info, Folder, StickyNote, ScanEye, X,
  CheckSquare, Square, ListChecks, Loader2, Play
} from 'lucide-react';
import { api } from './api';
import type { Reel, StatusCounts, HealthStatus, ArchiveStatus, LibraryItem } from './api';
import { ArchivePanel } from './ArchivePanel';
import { StoragePanel } from './StoragePanel';
import { ReelPreview } from './ReelPreview';
import { useAnalysisQueue } from './useAnalysisQueue';
import { FolderSidebar, FolderLocation } from './FolderNavigation';
import { DuplicateCopiesDialog } from './DuplicateCopiesDialog';
import {
  buildLibraryIndex,
  filterReelsByFolder,
  getRelativeFolder,
  folderKey,
  exactCopyKey,
  groupExactCopies,
} from './folders';

export default function App() {
  const [activeTab, setActiveTab] = useState<'all' | 'draft' | 'needs_review' | 'ready' | 'posted' | 'archived' | 'settings'>('all');
  const [reels, setReels] = useState<Reel[]>([]);
  const [libraryItems, setLibraryItems] = useState<LibraryItem[]>([]);
  const [groupCopies, setGroupCopies] = useState(true);
  const [copyGroupKey, setCopyGroupKey] = useState<string | null>(null);
  const [stats, setStats] = useState<StatusCounts | null>(null);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [editingReel, setEditingReel] = useState<Reel | null>(null);
  const [selectedFolder, setSelectedFolder] = useState<string | null>(null);
  const [quickLookReel, setQuickLookReel] = useState<Reel | null>(null);
  const [previewReelId, setPreviewReelId] = useState<number | null>(null);
  const closePreview = useCallback(() => setPreviewReelId(null), []);
  const [archiveStatus, setArchiveStatus] = useState<ArchiveStatus | null>(null);
  const [availability, setAvailability] = useState('');
  const [gridPage, setGridPage] = useState({ key: '', limit: 60 });
  const [hasQuickSummary, setHasQuickSummary] = useState<boolean | null>(null);
  
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

  const requestVersion = useRef(0);
  const loadData = useCallback(async (background = false) => {
    const request = ++requestVersion.current;
    if (!background) setLoading(true);
    try {
      const params: Parameters<typeof api.getReels>[0] = {
        search: searchTerm || undefined,
        has_final_post: hasFinalPost ?? undefined,
        has_ai_summary: hasAiSummary ?? undefined,
        has_quick_summary: hasQuickSummary ?? undefined,
        availability: availability || undefined,
      };
      if (activeTab !== 'all' && activeTab !== 'settings') params.status = activeTab;
      const [counts, health, list, archive, library] = await Promise.all([
        api.getStats(), api.getHealth(), api.getReels(params), api.getArchiveStatus(), api.getLibraryIndex(),
      ]);
      if (request !== requestVersion.current) return;
      setStats(counts); setHealth(health); setReels(list); setArchiveStatus(archive);
      setLibraryItems(library);
    } catch (error) {
      if (!background) addToast(error instanceof Error ? error.message : 'Failed to load archive.', 'error');
    } finally {
      if (request === requestVersion.current) setLoading(false);
    }
  }, [activeTab, searchTerm, hasFinalPost, hasAiSummary, hasQuickSummary, availability, addToast]);

  useEffect(() => {
    const initial = setTimeout(() => { void loadData(); }, 200);
    const poll = setInterval(() => { void loadData(true); }, 10000);
    const invalidate = () => { requestVersion.current++; };
    return () => { clearTimeout(initial); clearInterval(poll); invalidate(); };
  }, [loadData]);

  const reelsRoot = health?.reels_folder_path || '';
  const library = useMemo(
    () => buildLibraryIndex(libraryItems, reelsRoot, availability === 'missing'),
    [libraryItems, reelsRoot, availability]
  );
  // Null is the home destination, not "all locations". Derive it from the source
  // index so it works both on the Mac root and inside the Dropbox wrapper folder.
  const currentFolder = library.nodes.get(folderKey(selectedFolder ?? library.home.path, reelsRoot)) || library.home;
  const folderReels = useMemo(
    () => activeTab === 'all' ? filterReelsByFolder(reels, reelsRoot, currentFolder.path) : reels,
    [reels, reelsRoot, currentFolder.path, activeTab]
  );
  const displayedReels = useMemo(
    () => groupCopies ? groupExactCopies(folderReels) : folderReels,
    [folderReels, groupCopies]
  );
  const duplicateCopies = copyGroupKey ? library.copies.get(copyGroupKey) : undefined;

  const gridKey = JSON.stringify([activeTab, searchTerm, hasFinalPost, hasAiSummary, hasQuickSummary, availability, currentFolder.path, groupCopies]);
  useEffect(() => () => closePreview(), [gridKey, closePreview]);
  const visibleLimit = gridPage.key === gridKey ? gridPage.limit : 60;
  const renderedReels = displayedReels.slice(0, visibleLimit);

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
    // Analysis updates never reset an in-progress manual draft.
    setEditingReel(current => current?.id === updated.id ? {
      ...current, ai_summary: updated.ai_summary, ai_suggested_post_text: updated.ai_suggested_post_text,
      ai_suggested_hashtags: updated.ai_suggested_hashtags, ai_category: updated.ai_category,
      ai_platform_suggestion: updated.ai_platform_suggestion, ai_quality_notes: updated.ai_quality_notes,
    } : current);
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
    setSelectedIds(new Set(renderedReels.map(r => r.id)));
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

  const formValuesRef = useRef({ status: statusInput as Reel['status'], approved: approvedInput,
    manual_post_text: manualPostInput, final_post_text: finalPostInput, hashtags: hashtagsInput, notes: notesInput });
  useLayoutEffect(() => {
    formValuesRef.current = { status: statusInput as Reel['status'], approved: approvedInput,
      manual_post_text: manualPostInput, final_post_text: finalPostInput, hashtags: hashtagsInput, notes: notesInput };
  }, [statusInput, approvedInput, manualPostInput, finalPostInput, hashtagsInput, notesInput]);

  const persistReel = useCallback(async (options?: { silent?: boolean; reelId?: number }) => {
    const silent = options?.silent ?? false;
    const reelId = options?.reelId ?? editingReel?.id;
    if (!reelId || savingLockRef.current) return false;

    const payload = { ...formValuesRef.current };

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
        if (JSON.stringify(formValuesRef.current) === JSON.stringify(payload)) syncFormFromReel(updated);
      }
      setReels(prev => prev.map(r => (r.id === updated.id ? updated : r)));
      api.getStats().then(setStats).catch(() => {});
      setSaveStatus('saved');
      if (!silent) addToast('Draft saved to database.', 'success');
      return true;
    } catch (error: unknown) {
      setSaveStatus('error');
      addToast((error instanceof Error ? error.message : '') || 'Failed to save reel details.', 'error');
      return false;
    } finally {
      savingLockRef.current = false;
      setSaving(false);
    }
  }, [
    editingReel,
    formDiffersFromBaseline,
    addToast,
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
      return;
    }

    if (autosaveTimerRef.current) clearTimeout(autosaveTimerRef.current);
    autosaveTimerRef.current = setTimeout(() => {
      setSaveStatus('pending');
      void persistReel({ silent: true });
    }, 600);

    return () => {
      if (autosaveTimerRef.current) clearTimeout(autosaveTimerRef.current);
    };
  }, [
    editingReel,
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

  const getCaptionPreview = (reel: Reel) => {
    if (reel.final_post_text?.trim()) return reel.final_post_text;
    if (reel.manual_post_text?.trim()) return reel.manual_post_text;
    if (reel.notes?.trim()) return `[Note] ${reel.notes}`;
    if (reel.quick_summary) return reel.quick_summary;
    if (reel.ai_summary) return reel.ai_summary;
    return 'Waiting for a quick description. Open workbench to add notes.';
  };

  const handleQuickLook = (reel: Reel) => {
    setPreviewReelId(null);
    setQuickLookReel(reel);
    if (!reel.thumbnail_path) {
      void api.generateThumbnail(reel.id).then(updated => {
        setReels(prev => prev.map(r => (r.id === updated.id ? updated : r)));
      }).catch(() => {});
    }
  };

  const handleScan = async () => {
    setScanning(true);
    addToast("Checking folder contents, moves, renames and deletions...", "warning");
    try {
      const result = await api.scanFolder();
      addToast(
        `Scan complete: ${result.scanned_count} files, ${result.added_count} new, ${result.moved_count ?? 0} moved/renamed, ${result.missing_count} missing, ${result.skipped_count} empty or still arriving.`,
        "success"
      );
      await loadData();
    } catch (error: unknown) {
      addToast((error instanceof Error ? error.message : '') || "Failed to scan folder.", "error");
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
      if (!await persistReel({ silent: true, reelId: editingReel.id })) return false;
    }
    editingIdRef.current = null;
    saveBaselineRef.current = null;
    setEditingReel(null);
    setSaveStatus('idle');
    return true;
  };

  const handleSelectReel = async (reel: Reel) => {
    setPreviewReelId(null);
    if (editingReel?.id === reel.id) return;

    if (editingReel && editingReel.id !== reel.id) {
      if (autosaveTimerRef.current) clearTimeout(autosaveTimerRef.current);
      if (!await persistReel({ silent: true, reelId: editingReel.id })) return false;
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
      const fields = formValuesRef.current;
      if (!formDiffersFromBaseline(reel, { status: fields.status, approved: fields.approved,
        manual: fields.manual_post_text, final: fields.final_post_text, hashtags: fields.hashtags, notes: fields.notes })) {
        syncFormFromReel(fresh);
      }
      setReels(prev => prev.map(r => (r.id === fresh.id ? fresh : r)));
    } catch {
      addToast('Could not refresh reel from server.', 'warning');
    }
  };

  const clearFilters = () => {
    setSearchTerm(''); setHasFinalPost(null); setHasAiSummary(null);
    setHasQuickSummary(null); setAvailability(''); clearSelection();
  };

  const handleNavigateFolder = async (path: string) => {
    if (!await handleCloseWorkbench()) return;
    setSelectedFolder(path); setActiveTab('all'); setSelectionMode(false);
    setCopyGroupKey(null); clearFilters();
  };

  const handleOpenCopy = async (id: number) => {
    const copy = await api.getReel(id);
    return (await handleSelectReel(copy)) !== false;
  };

  const handleSaveReel = async () => {
    if (autosaveTimerRef.current) clearTimeout(autosaveTimerRef.current);
    await persistReel();
  };

  const handleAnalyze = (id: number) => {
    const reel = reels.find(r => r.id === id) || (editingReel?.id === id ? editingReel : null);
    if (reel) enqueueAnalysis([reel]);
  };

  const handleUseAiCaption = () => {
    if (editingReel?.ai_suggested_post_text) setFinalPostInput(editingReel.ai_suggested_post_text);
  };
  const handleUseAiHashtags = () => {
    if (editingReel?.ai_suggested_hashtags) setHashtagsInput(editingReel.ai_suggested_hashtags);
  };

  const handleMarkReady = async (id: number) => {
    if (editingReel?.id === id && !await persistReel({ silent: true })) return;
    try {
      const updated = await api.markReady(id);
      addToast("Reel approved and pushed to the Ready Queue!", "success");
      if (editingReel && editingReel.id === id) {
        setEditingReel(updated);
        setStatusInput(updated.status);
        setApprovedInput(updated.approved);
      }
      loadData();
    } catch (error: unknown) {
      addToast((error instanceof Error ? error.message : '') || "Ready verification failed. A final caption is required.", "error");
    }
  };

  const handleMarkPosted = async (id: number) => {
    if (editingReel?.id === id && !await persistReel({ silent: true })) return;
    try {
      const updated = await api.markPosted(id);
      addToast("Reel marked as posted on social media.", "success");
      if (editingReel && editingReel.id === id) {
        setEditingReel(updated);
        setStatusInput(updated.status);
      }
      loadData();
    } catch (error: unknown) {
      addToast(error instanceof Error ? error.message : 'Action failed.', "error");
    }
  };

  const handleArchive = async (id: number) => {
    if (editingReel?.id === id && !await persistReel({ silent: true })) return;
    if (!window.confirm("Are you sure you want to archive this reel?")) return;
    try {
      const updated = await api.archiveReel(id);
      addToast("Reel sent to archives.", "success");
      if (editingReel && editingReel.id === id) {
        setEditingReel(updated);
        setStatusInput(updated.status);
      }
      loadData();
    } catch (error: unknown) {
      addToast(error instanceof Error ? error.message : 'Action failed.', "error");
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

  return (
    <div className="h-screen overflow-hidden bg-plum-950 flex font-sans select-none relative retro-scanlines">
      {duplicateCopies && <DuplicateCopiesDialog copies={duplicateCopies} reelsRoot={reelsRoot}
        onClose={() => setCopyGroupKey(null)} onOpen={handleOpenCopy} />}
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
      <aside className="w-64 border-r border-plum-800 bg-plum-950/90 hidden md:flex flex-col shrink-0">
        {/* Brand Logo */}
        <div className="h-20 flex items-center gap-3 px-6 border-b border-plum-800">
          <Film className="w-8 h-8 text-neon-cyan animate-pulse" />
          <div>
            <h1 className="text-xl font-retro font-bold tracking-widest text-transparent bg-clip-text bg-gradient-to-r from-neon-cyan to-neon-pink text-retro-glow">
              REELVAULT
            </h1>
            <p className="text-[9px] font-pixel text-neon-pink/80 tracking-tighter">ARCHIVE QUEUE</p>
          </div>
        </div>

        {/* Tab Items */}
        <nav className="flex-1 px-4 py-6 flex flex-col gap-2">
          {[
            { id: 'all', label: 'Home', icon: Film },
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
                onClick={async () => { if (!await handleCloseWorkbench()) return; setSelectedFolder(null); setSelectionMode(false); clearSelection(); setActiveTab(tab.id as typeof activeTab); if (tab.id === 'all') clearFilters(); }}
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
                    {tab.id === 'all' ? library.home.count : stats[tab.id as keyof StatusCounts]}
                  </span>
                )}
              </button>
            );
          })}
          <p className="text-[10px] text-purple-400/70 px-4 mt-2 leading-relaxed">Home shows your main folder. Workflow queues span all folders; their counts include copies.</p>
        </nav>

        {/* System Health Summary & Settings link */}
        <div className="p-4 border-t border-plum-800 bg-plum-950/50 flex flex-col gap-3">
          <button 
            onClick={async () => { if (await handleCloseWorkbench()) setActiveTab('settings'); }}
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
            <span className="opacity-80">v2.0.0</span>
          </div>
        </div>
      </aside>

      {/* Main Command Workspace */}
      <main className="flex-1 flex flex-col min-w-0 bg-plum-900/20 overflow-hidden">
        {/* Top App Bar */}
        <header className="h-20 border-b border-plum-800 px-3 md:px-8 flex items-center justify-between gap-2 shrink-0 glass-panel">
          <div className="flex items-center gap-3">
            <select aria-label="Navigate archive" value={activeTab} className="md:hidden max-w-36 bg-plum-950 border border-plum-700 rounded-lg p-2 text-sm text-neon-cyan"
              onChange={async event => {
                const tab = event.target.value as typeof activeTab;
                if (!await handleCloseWorkbench()) return;
                closePreview(); setSelectedFolder(null); setSelectionMode(false); clearSelection(); setActiveTab(tab);
                if (tab === 'all') clearFilters();
              }}>
              <option value="all">Home</option><option value="draft">Drafts</option>
              <option value="needs_review">Needs Review</option><option value="ready">Ready Queue</option>
              <option value="posted">Posted</option><option value="archived">Archived</option><option value="settings">Settings</option>
            </select>
            <h2 className="sr-only md:not-sr-only md:text-xl font-retro font-semibold tracking-wider text-white">
              {activeTab === 'settings' ? 'SETTINGS CONTROL' : activeTab === 'all' ? 'REEL LIBRARY' : `${activeTab.replace('_', ' ').toUpperCase()} ARCHIVE`}
            </h2>
            {activeTab !== 'settings' && displayedReels.length > 0 && (
              <span className="text-xs px-2.5 py-0.5 rounded-full bg-plum-800 text-purple-300 font-bold border border-plum-700">
                {displayedReels.length} Reels
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
                <span className="sr-only sm:not-sr-only">{selectionMode ? 'Done Selecting' : 'Select Reels'}</span>
              </button>
            )}
            {activeTab !== 'settings' && (
              <button 
                type="button"
                onClick={handleScan}
                disabled={scanning || archiveStatus?.scan.running}
                className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-neon-pink to-neon-orange text-white rounded-lg text-sm font-semibold border border-neon-pink hover:opacity-90 active:scale-95 shadow-[0_0_10px_rgba(255,0,127,0.4)] disabled:opacity-50 transition-all cursor-pointer"
              >
                <RefreshCw className={`w-4 h-4 ${scanning || archiveStatus?.scan.running ? 'animate-spin' : ''}`} />
                <span className="sr-only sm:not-sr-only">{scanning || archiveStatus?.scan.running ? 'Scanning…' : 'Rescan Folder'}</span>
              </button>
            )}
          </div>
        </header>

        {/* Content Box */}
        <div className="flex-1 p-3 md:p-8 flex gap-8 overflow-hidden min-h-0">
          {activeTab === 'settings' ? (
            /* Settings View Page */
            <div className="w-full max-w-3xl flex flex-col gap-6 overflow-y-auto pr-2">
              <StoragePanel />
              <ArchivePanel status={archiveStatus} onRefresh={() => void loadData(true)} onToast={addToast} onScan={() => void handleScan()} />
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
                        <p className="text-green-400 text-sm font-semibold">Gemini key configured</p>
                        <p className="text-xs text-green-300/80 mt-0.5">An API key is configured. Click "Analyze" on any reel detail card to have the AI write suggestions and summarize events.</p>
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
                <div className="text-xs text-purple-300 flex flex-wrap items-center gap-3" role="status">
                  <span>{archiveStatus?.scan.running ? 'Scanning for new reels…' : archiveStatus?.scan.finished_at ? `Last scan ${new Date(archiveStatus.scan.finished_at).toLocaleTimeString()}` : 'Connecting to archive…'}</span>
                  <span>· {archiveStatus?.described || 0} described</span>
                  <button className="text-neon-cyan underline cursor-pointer" onClick={async () => { if (await handleCloseWorkbench()) setActiveTab('settings'); }}>
                    {archiveStatus?.paused ? 'Descriptions paused' : `${archiveStatus?.jobs.queued || 0} descriptions queued`} · Manage
                  </button>
                  {archiveStatus?.scan.error && <span className="text-amber-300">Scan needs attention — see Settings</span>}
                </div>
                {/* Filters Row */}
                <div className="glass-panel p-4 rounded-xl border border-plum-800 flex flex-wrap gap-4 items-center justify-between shadow-md">
                  <div className="relative flex-1 min-w-[240px]">
                    <Search className="w-4 h-4 text-purple-400 absolute left-3 top-1/2 -translate-y-1/2" />
                    <input 
                      type="text"
                      aria-label={activeTab === 'all' ? 'Search this folder' : 'Search workflow queue'}
                      placeholder={activeTab === 'all' ? 'Search this folder: descriptions, tags, notes…' : 'Search descriptions, subjects, tags, captions, notes…'}
                      value={searchTerm}
                      onChange={e => setSearchTerm(e.target.value)}
                      className="w-full bg-plum-950 border border-plum-800 rounded-lg pl-10 pr-4 py-2 text-sm text-white focus:outline-none focus:border-neon-cyan/80 transition-all font-sans"
                    />
                  </div>
                  
                  <div className="flex items-center gap-4 flex-wrap">
                    <select aria-label="File availability" value={availability} onChange={e => setAvailability(e.target.value)} className="bg-plum-950 border border-plum-800 text-xs text-purple-200 rounded-lg p-2">
                      <option value="">Available files</option><option value="local">On this Mac</option><option value="cloud">Offloaded</option><option value="missing">Missing files (history)</option>
                    </select>
                    <select aria-label="Quick description" value={hasQuickSummary === null ? '' : String(hasQuickSummary)} onChange={e => setHasQuickSummary(e.target.value === '' ? null : e.target.value === 'true')} className="bg-plum-950 border border-plum-800 text-xs text-purple-200 rounded-lg p-2">
                      <option value="">Any description</option><option value="true">Quick description saved</option><option value="false">No quick description</option>
                    </select>
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
                      <span className="text-xs text-purple-400 uppercase font-bold">Full review:</span>
                      <select 
                        value={hasAiSummary === null ? 'all' : String(hasAiSummary)}
                        onChange={e => setHasAiSummary(e.target.value === 'all' ? null : e.target.value === 'true')}
                        className="bg-plum-950 border border-plum-800 text-xs text-purple-200 rounded-lg p-2 focus:outline-none"
                      >
                        <option value="all">All Reels</option>
                        <option value="true">Reviewed Only</option>
                        <option value="false">Not Reviewed</option>
                      </select>
                    </div>
                  </div>
                </div>

                {/* Scrollable Reels List Grid Container */}
                <div className="flex-1 flex gap-4 min-h-0 overflow-hidden">
                  {activeTab === 'all' && reelsRoot && <FolderSidebar library={library} current={currentFolder}
                    reelsRoot={reelsRoot} onNavigate={path => { void handleNavigateFolder(path); }} />}

                  <div className="flex-1 overflow-y-auto pr-1 min-w-0">
                  {activeTab === 'all' && reelsRoot && <FolderLocation library={library} current={currentFolder}
                    reelsRoot={reelsRoot} onNavigate={path => { void handleNavigateFolder(path); }} />}
                  <div className="flex flex-wrap items-center justify-between gap-3 mb-4 text-xs text-purple-300">
                    <p aria-live="polite">{displayedReels.length.toLocaleString()} {groupCopies ? 'unique reels' : 'files'}
                      {activeTab === 'all' ? ' in this folder' : ' across all folders'}
                      {groupCopies && folderReels.length > displayedReels.length && <span className="text-purple-400"> · {folderReels.length - displayedReels.length} extra copies grouped</span>}
                    </p>
                    <label className="flex items-center gap-2 cursor-pointer rounded focus-within:outline-neon-cyan">
                      <input type="checkbox" checked={groupCopies} onChange={event => { setGroupCopies(event.target.checked); clearSelection(); }} className="accent-cyan-400" />
                      Group exact copies
                    </label>
                  </div>
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
                        <p className="text-lg font-retro font-bold text-purple-300">{activeTab === 'all' ? 'No matching reels in this folder' : 'No matching reels'}</p>
                        <p className="text-sm text-purple-400/80 mt-1 max-w-sm">{activeTab === 'all' && currentFolder.children.length ? 'Choose a folder above to see its reels. Files in subfolders are not included here.' : 'Try clearing your filters, or rescan after adding new videos.'}</p>
                        <button type="button" onClick={clearFilters} className="archive-button mt-4">Clear filters</button>
                      </div>
                    </div>
                  ) : (
                    <div className="grid grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-6 pb-6">
                      {renderedReels.map(reel => {
                        const hasFinalCaption = reel.final_post_text && reel.final_post_text.trim();
                        const hasManualDraft = reel.manual_post_text && reel.manual_post_text.trim();
                        const hasNotes = reel.notes && reel.notes.trim();
                        const isEditing = editingReel?.id === reel.id;
                        const folderLabel = reelsRoot ? getRelativeFolder(reel.filepath, reelsRoot) : '';
                        const copies = library.copies.get(exactCopyKey(reel));
                        
                        return (
                          <div 
                            key={reel.id} 
                            onClick={() => {
                              setPreviewReelId(null);
                              if (selectionMode) {
                                toggleReelSelection(reel.id);
                                return;
                              }
                              void handleSelectReel(reel);
                            }}
                            className={`glass-panel rounded-xl border cursor-pointer overflow-hidden transition-all duration-300 flex flex-col min-h-[530px] group shadow-md hover:-translate-y-1.5 ${
                              isEditing 
                                ? 'border-neon-cyan animate-pulse-cyan' 
                                : selectedIds.has(reel.id)
                                  ? 'border-neon-pink ring-2 ring-neon-pink/40'
                                  : 'border-plum-800 hover:border-neon-cyan/50 hover:shadow-[0_0_12px_rgba(0,240,255,0.15)]'
                            }`}
                          >
                            {/* Card Thumbnail / Header Preview */}
                            <div className="h-[340px] bg-plum-950 relative overflow-hidden flex items-center justify-center shrink-0 border-b border-plum-850">
                              {previewReelId === reel.id ? <ReelPreview key={`${reel.id}:${reel.source_version}`}
                                reelId={reel.id} filename={reel.filename} onClose={closePreview}
                                onFullVideo={() => handleQuickLook(reel)} /> : !selectionMode && reel.storage_status !== 'missing' && (
                                <button type="button" aria-label={`Preview ${reel.filename}`}
                                  onClick={event => {
                                    event.stopPropagation();
                                    document.querySelectorAll('video').forEach(video => video.pause());
                                    setQuickLookReel(null); setPreviewReelId(reel.id);
                                  }}
                                  className="absolute bottom-12 left-1/2 -translate-x-1/2 z-20 flex items-center gap-2 rounded-full px-4 py-2 bg-plum-950/95 border border-neon-cyan/70 text-neon-cyan text-xs font-bold shadow-lg hover:bg-neon-cyan hover:text-plum-950 focus-visible:outline-2 focus-visible:outline-white">
                                  <Play size={15} fill="currentColor" /> Preview
                                </button>
                              )}
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
                                  style={{ backgroundImage: `url(/thumbnails/${encodeURIComponent(reel.thumbnail_path)})` }}
                                />
                              )}
                              
                              {reel.thumbnail_path ? (
                                <img loading="lazy" decoding="async"
                                  src={`/thumbnails/${encodeURIComponent(reel.thumbnail_path)}`}
                                  alt={reel.filename} 
                                  className="h-full aspect-[9/16] object-contain relative z-10 group-hover:scale-102 transition-all duration-500 shadow-lg"
                                />
                              ) : (
                                <div className="w-full h-full bg-gradient-to-tr from-plum-800 via-plum-900 to-plum-950 flex flex-col items-center justify-center gap-2 relative z-10">
                                  <Video className="w-10 h-10 text-purple-500/60" />
                                  <span className="text-[10px] text-purple-400 font-bold uppercase tracking-wider">No Thumbnail</span>
                                </div>
                              )}

                              <span className="absolute bottom-2 left-2 z-20 px-2 py-1 rounded bg-black/80 text-[10px] text-purple-100">
                                {reel.storage_status === 'cloud' ? 'Offloaded' : reel.storage_status === 'missing' ? 'Missing / moved' : reel.storage_status === 'local' ? 'On this Mac' : 'Checking storage'}
                              </span>
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

                                <button type="button" onClick={event => { event.stopPropagation(); void handleNavigateFolder(folderLabel); }}
                                  className="text-[10px] text-purple-400/90 hover:text-neon-cyan font-mono flex items-center gap-1 text-left min-w-0 rounded focus-visible:outline-neon-cyan" title={`Open ${folderLabel || library.root.name}`}>
                                    <Folder className="w-3 h-3 shrink-0" />
                                    <span className="truncate">{folderLabel || library.root.name}</span>
                                </button>
                                {copies && copies.length > 1 && <button type="button"
                                  onClick={event => { event.stopPropagation(); setCopyGroupKey(exactCopyKey(reel)); }}
                                  className="self-start flex items-center gap-1.5 text-[11px] px-2 py-1 rounded-md bg-neon-cyan/10 text-neon-cyan border border-neon-cyan/25 hover:bg-neon-cyan/20 focus-visible:outline-neon-cyan">
                                  <Copy size={12} />{copies.length} exact copies · View
                                </button>}

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
                                        title="Queue full video review + captions"
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
                  {!loading && renderedReels.length < displayedReels.length && (
                    <button className="archive-button mb-6 w-full justify-center" onClick={() => setGridPage({ key: gridKey, limit: visibleLimit + 60 })}>
                      Show 60 more · {renderedReels.length} of {displayedReels.length}
                    </button>
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
                          style={{ backgroundImage: `url(/thumbnails/${encodeURIComponent(editingReel.thumbnail_path)})` }}
                        />
                      )}
                      <video 
                        key={editingReel.id} 
                        src={`/api/reels/${editingReel.id}/video`}
                        controls 
                        className="h-full aspect-[9/16] object-contain relative z-10 shadow-2xl"
                        preload="none"
                        poster={editingReel.thumbnail_path ? `/thumbnails/${encodeURIComponent(editingReel.thumbnail_path)}` : undefined}
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

                    {(editingReel.quick_summary || reels.find(r => r.id === editingReel.id)?.quick_summary) && (() => {
                      const described = reels.find(r => r.id === editingReel.id) || editingReel;
                      return <div className="p-4 rounded-lg border border-neon-cyan/30 bg-plum-950 flex flex-col gap-2">
                        <h4 className="text-xs text-neon-cyan font-bold uppercase">Quick archive description</h4>
                        <p className="text-sm text-purple-100 select-text">{described.quick_summary}</p>
                        <p className="text-xs text-purple-300">{described.quick_category} · {described.quick_tags}</p>
                        <p className="text-[11px] text-purple-400">{described.quick_summary_source === 'cached_thumbnail' ? 'Based on one cached thumbnail' : 'Based on a few sampled frames'} · No audio review</p>
                      </div>;
                    })()}
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
                            <span>{getReelQueueStatus(editingReel.id) === 'queued' ? 'QUEUED FOR ANALYSIS' : 'FULL VIDEO REVIEW + CAPTION'}</span>
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
            Select all visible ({renderedReels.length})
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
            Full video review + captions
          </button>
          <button type="button" disabled={selectedIds.size === 0} className="archive-button" onClick={async () => {
            try {
              const result = await api.describeMissing([...selectedIds], true);
              addToast(`${result.queued} quick descriptions queued.`, 'success');
              clearSelection(); setSelectionMode(false); void loadData(true);
            } catch (error) { addToast(error instanceof Error ? error.message : 'Could not queue descriptions.', 'error'); }
          }}>Quick descriptions</button>
        </div>
      )}

      {/* AI analysis queue panel */}
      {analysisQueue.length > 0 && (
        <div className="fixed bottom-6 right-5 z-[150] w-80 glass-panel border border-plum-700 rounded-xl shadow-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-plum-800 flex items-center justify-between bg-plum-950/80">
            <div className="flex items-center gap-2">
              <Sparkles className={`w-4 h-4 text-neon-pink ${analysisProcessing ? 'animate-pulse' : ''}`} />
              <span className="text-xs font-bold uppercase text-white tracking-wider">Full Video Review Queue</span>
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
              Keep this tab open for full reviews · {queuedCount} waiting
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
