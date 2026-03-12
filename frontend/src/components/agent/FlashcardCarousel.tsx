import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

export interface FlashcardItem {
  id: string;
  title?: string;
  subtitle?: string;
  content: ReactNode;
}

interface FlashcardCarouselProps {
  items: FlashcardItem[];
  activeIndex?: number;
  onActiveIndexChange?: (index: number) => void;
  className?: string;
  cardClassName?: string;
}

export function FlashcardCarousel({
  items,
  activeIndex,
  onActiveIndexChange,
  className = '',
  cardClassName = '',
}: FlashcardCarouselProps) {
  const trackRef = useRef<HTMLDivElement | null>(null);
  const [internalIndex, setInternalIndex] = useState(0);
  const [isUserScrolling, setIsUserScrolling] = useState(false);
  // During smooth programmatic scroll (dot/arrow click or "snap back" alignment),
  // ignore onScroll-derived index updates. Otherwise the carousel can "bounce back"
  // to the previous card because nearest-index calculations happen mid-animation.
  const isProgrammaticScrollRef = useRef(false);
  const programmaticScrollTimerRef = useRef<number | null>(null);
  const resolvedIndex = activeIndex ?? internalIndex;
  const total = items.length;

  const ids = useMemo(() => items.map((item) => item.id), [items]);

  const markProgrammaticScroll = () => {
    isProgrammaticScrollRef.current = true;
    if (programmaticScrollTimerRef.current) {
      window.clearTimeout(programmaticScrollTimerRef.current);
    }
    // Keep the window short; just long enough to cover the smooth scroll animation.
    programmaticScrollTimerRef.current = window.setTimeout(() => {
      isProgrammaticScrollRef.current = false;
      programmaticScrollTimerRef.current = null;
    }, 480);
  };

  useEffect(() => {
    return () => {
      if (programmaticScrollTimerRef.current) {
        window.clearTimeout(programmaticScrollTimerRef.current);
        programmaticScrollTimerRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (resolvedIndex < 0 || resolvedIndex >= total) return;
    const track = trackRef.current;
    if (!track || isUserScrolling) return;
    const target = track.children.item(resolvedIndex) as HTMLElement | null;
    if (!target) return;
    markProgrammaticScroll();
    track.scrollTo({
      left: target.offsetLeft,
      behavior: 'smooth',
    });
  }, [resolvedIndex, total, isUserScrolling, ids]);

  const updateIndex = (nextIndex: number) => {
    const bounded = Math.max(0, Math.min(nextIndex, total - 1));
    if (activeIndex === undefined) {
      setInternalIndex(bounded);
    }
    onActiveIndexChange?.(bounded);
  };

  const handleScroll = () => {
    const track = trackRef.current;
    if (!track || total <= 1) return;
    if (isProgrammaticScrollRef.current) return;
    const scrollLeft = track.scrollLeft;
    let nearest = 0;
    let minDiff = Number.POSITIVE_INFINITY;
    for (let i = 0; i < track.children.length; i += 1) {
      const child = track.children.item(i) as HTMLElement | null;
      if (!child) continue;
      const diff = Math.abs(child.offsetLeft - scrollLeft);
      if (diff < minDiff) {
        minDiff = diff;
        nearest = i;
      }
    }
    updateIndex(nearest);
  };

  useEffect(() => {
    if (!isUserScrolling) return;
    const timer = window.setTimeout(() => setIsUserScrolling(false), 120);
    return () => window.clearTimeout(timer);
  }, [isUserScrolling, resolvedIndex]);

  if (total === 0) {
    return null;
  }

  return (
    <div className={`space-y-2 ${className}`}>
      <div className="flex items-center justify-between text-xs text-gray-600 dark:text-gray-300">
        <div>
          {resolvedIndex + 1}/{total}
        </div>
        <div className="inline-flex items-center gap-1">
          <button
            type="button"
            disabled={resolvedIndex <= 0}
            onClick={() => updateIndex(resolvedIndex - 1)}
            className="rounded border border-gray-300 dark:border-gray-600 p-1 text-gray-600 dark:text-gray-300 disabled:cursor-not-allowed disabled:opacity-40"
            aria-label="上一张卡片"
          >
            <ChevronLeft className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            disabled={resolvedIndex >= total - 1}
            onClick={() => updateIndex(resolvedIndex + 1)}
            className="rounded border border-gray-300 dark:border-gray-600 p-1 text-gray-600 dark:text-gray-300 disabled:cursor-not-allowed disabled:opacity-40"
            aria-label="下一张卡片"
          >
            <ChevronRight className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      <div
        ref={trackRef}
        onScroll={() => {
          if (isProgrammaticScrollRef.current) return;
          setIsUserScrolling(true);
          handleScroll();
        }}
        className="flex snap-x snap-mandatory gap-3 overflow-x-auto pb-1 scroll-smooth"
      >
        {items.map((item) => (
          <section
            key={item.id}
            className={`w-full shrink-0 snap-start rounded-xl border border-gray-200 dark:border-gray-700 bg-white/90 dark:bg-gray-900/50 p-2.5 ${cardClassName}`}
          >
            {(item.title || item.subtitle) && (
              <div className="mb-2">
                {item.title && (
                  <div className="text-xs font-medium text-gray-800 dark:text-gray-200">
                    {item.title}
                  </div>
                )}
                {item.subtitle && (
                  <div className="mt-0.5 text-[11px] text-gray-500 dark:text-gray-400">
                    {item.subtitle}
                  </div>
                )}
              </div>
            )}
            {item.content}
          </section>
        ))}
      </div>

      <div className="flex items-center justify-center gap-1">
        {items.map((item, idx) => (
          <button
            key={`${item.id}-dot`}
            type="button"
            onClick={() => updateIndex(idx)}
            className={`h-1.5 rounded-full transition-all ${
              idx === resolvedIndex
                ? 'w-4 bg-emerald-500'
                : 'w-1.5 bg-gray-300 dark:bg-gray-600'
            }`}
            aria-label={`跳到第 ${idx + 1} 张卡片`}
          />
        ))}
      </div>
    </div>
  );
}
