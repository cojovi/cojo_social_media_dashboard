import { useEffect, useLayoutEffect, useRef, useState } from 'react';

const BATCH_SIZE = 60;

/** Reveal cards in batches inside the grid's own scroller; never request video bytes. */
export function useInfiniteReels(viewKey: string, total: number, loading: boolean) {
  const [page, setPage] = useState({ key: viewKey, limit: BATCH_SIZE });
  const scrollRef = useRef<HTMLDivElement>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);

  // Reset on every view change, including returning to an earlier folder/filter.
  // Adjust before commit so an old observer cannot append to the new view.
  if (page.key !== viewKey) setPage({ key: viewKey, limit: BATCH_SIZE });
  const limit = page.key === viewKey ? page.limit : BATCH_SIZE;
  const hasMore = limit < total;

  useLayoutEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = 0;
  }, [viewKey]);

  useEffect(() => {
    const root = scrollRef.current;
    const sentinel = sentinelRef.current;
    if (loading || !hasMore || !root || !sentinel) return;
    let active = true;
    let frame = 0;
    const observer = new IntersectionObserver(entries => {
      if (!active || !entries.some(entry => entry.isIntersecting)) return;
      // One append per observed batch, even if several intersection events arrive.
      observer.disconnect();
      frame = requestAnimationFrame(() => {
        if (!active) return;
        setPage(current => current.key === viewKey && current.limit === limit
          ? { key: viewKey, limit: Math.min(limit + BATCH_SIZE, total) }
          : current);
      });
    }, { root, rootMargin: '0px 0px 320px 0px', threshold: 0 });
    observer.observe(sentinel);
    return () => { active = false; observer.disconnect(); cancelAnimationFrame(frame); };
  }, [viewKey, total, limit, loading, hasMore]);

  return { limit, hasMore, scrollRef, sentinelRef };
}
