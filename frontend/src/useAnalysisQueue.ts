import { useCallback, useRef, useState } from 'react';
import { api, type Reel } from './api';

export type AnalysisQueueStatus = 'queued' | 'processing' | 'done' | 'failed';

export interface AnalysisQueueItem {
  id: number;
  filename: string;
  status: AnalysisQueueStatus;
  error?: string;
}

const QUEUE_DELAY_MS = 2500;

interface UseAnalysisQueueOptions {
  geminiConfigured: boolean;
  onReelUpdated: (reel: Reel) => void;
  onToast: (message: string, type: 'success' | 'error' | 'warning') => void;
}

export function useAnalysisQueue({
  geminiConfigured,
  onReelUpdated,
  onToast,
}: UseAnalysisQueueOptions) {
  const [queue, setQueue] = useState<AnalysisQueueItem[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const queueRef = useRef<AnalysisQueueItem[]>([]);
  const workerRunningRef = useRef(false);

  const syncQueue = useCallback((items: AnalysisQueueItem[]) => {
    queueRef.current = items;
    setQueue(items);
  }, []);

  const runWorker = useCallback(async () => {
    if (workerRunningRef.current) return;
    workerRunningRef.current = true;

    let succeeded = 0;
    let failed = 0;

    try {
      while (true) {
        const nextIndex = queueRef.current.findIndex(item => item.status === 'queued');
        if (nextIndex === -1) break;

        const current = queueRef.current[nextIndex];
        const updatedItems = queueRef.current.map((item, index) =>
          index === nextIndex ? { ...item, status: 'processing' as const } : item
        );
        syncQueue(updatedItems);
        setActiveId(current.id);

        try {
          const updated = await api.analyzeReel(current.id);
          onReelUpdated(updated);
          queueRef.current = queueRef.current.map(item =>
            item.id === current.id ? { ...item, status: 'done' as const } : item
          );
          syncQueue([...queueRef.current]);
          succeeded += 1;
        } catch (error: unknown) {
          const message = error instanceof Error ? error.message : 'Analysis failed';
          queueRef.current = queueRef.current.map(item =>
            item.id === current.id ? { ...item, status: 'failed' as const, error: message } : item
          );
          syncQueue([...queueRef.current]);
          failed += 1;
        }

        setActiveId(null);
        await new Promise(resolve => setTimeout(resolve, QUEUE_DELAY_MS));
      }
    } finally {
      workerRunningRef.current = false;
      setActiveId(null);
      if (succeeded + failed > 0) {
        onToast(
          `AI queue finished — ${succeeded} succeeded${failed ? `, ${failed} failed` : ''}.`,
          failed > 0 ? 'warning' : 'success'
        );
      }
    }
  }, [onReelUpdated, onToast, syncQueue]);

  const enqueue = useCallback(
    (reelsToAnalyze: Reel[]) => {
      if (!geminiConfigured) {
        onToast('Gemini API is not configured. Add GEMINI_API_KEY to your .env file.', 'error');
        return 0;
      }

      const busyIds = new Set(
        queueRef.current
          .filter(item => item.status === 'queued' || item.status === 'processing')
          .map(item => item.id)
      );

      const newItems: AnalysisQueueItem[] = [];
      for (const reel of reelsToAnalyze) {
        if (busyIds.has(reel.id)) continue;
        newItems.push({ id: reel.id, filename: reel.filename, status: 'queued' });
        busyIds.add(reel.id);
      }

      if (newItems.length === 0) {
        onToast('Those reels are already queued or processing.', 'warning');
        return 0;
      }

      const newIds = new Set(newItems.map(item => item.id));
      syncQueue([...queueRef.current.filter(item => !newIds.has(item.id)), ...newItems]);
      onToast(`Queued ${newItems.length} reel(s) for Gemini analysis.`, 'success');
      void runWorker();
      return newItems.length;
    },
    [geminiConfigured, onToast, runWorker, syncQueue]
  );

  const clearCompleted = useCallback(() => {
    syncQueue(queueRef.current.filter(item => item.status === 'queued' || item.status === 'processing'));
  }, [syncQueue]);

  const queuedCount = queue.filter(item => item.status === 'queued').length;
  const isProcessing = activeId !== null || queue.some(item => item.status === 'processing');

  return {
    queue,
    activeId,
    queuedCount,
    isProcessing,
    enqueue,
    clearCompleted,
  };
}
