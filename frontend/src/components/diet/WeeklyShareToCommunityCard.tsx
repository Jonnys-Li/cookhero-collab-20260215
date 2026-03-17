import { useMemo, useState } from 'react';
import { Loader2, Send, Sparkles } from 'lucide-react';

import type { WeeklySummary } from '../../types/diet';
import { createCommunityPost, polishCommunityPost } from '../../services/api/community';
import { trackEvent } from '../../services/api/events';

function toSnapshot(summary: WeeklySummary): Record<string, unknown> {
  return {
    week_start_date: summary.week_start_date,
    week_end_date: summary.week_end_date,
    total_calories: summary.total_calories,
    total_protein: summary.total_protein,
    total_fat: summary.total_fat,
    total_carbs: summary.total_carbs,
    avg_daily_calories: summary.avg_daily_calories,
  };
}

function buildDefaultContent(summary: WeeklySummary): string {
  const kcal = Number.isFinite(summary.total_calories) ? Math.round(summary.total_calories) : null;
  const avg = Number.isFinite(summary.avg_daily_calories) ? Math.round(summary.avg_daily_calories) : null;
  const protein = Number.isFinite(summary.total_protein) ? summary.total_protein.toFixed(0) : null;
  const fat = Number.isFinite(summary.total_fat) ? summary.total_fat.toFixed(0) : null;
  const carbs = Number.isFinite(summary.total_carbs) ? summary.total_carbs.toFixed(0) : null;

  return [
    '本周复盘：',
    `周期 ${summary.week_start_date} - ${summary.week_end_date}`,
    kcal !== null ? `总热量 ${kcal} kcal（日均 ${avg ?? '--'} kcal）` : '总热量 --',
    `宏量：P ${protein ?? '--'}g · F ${fat ?? '--'}g · C ${carbs ?? '--'}g`,
    '',
    '给自己一句鼓励：我在变得更稳定。',
  ].join('\n');
}

export function WeeklyShareToCommunityCard({
  token,
  weeklySummary,
  onShared,
}: {
  token: string;
  weeklySummary: WeeklySummary | null;
  onShared?: () => void | Promise<void>;
}) {
  const [sharing, setSharing] = useState(false);
  const [polishing, setPolishing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const snapshot = useMemo(() => (weeklySummary ? toSnapshot(weeklySummary) : null), [weeklySummary]);
  const defaultContent = useMemo(
    () => (weeklySummary ? buildDefaultContent(weeklySummary) : ''),
    [weeklySummary]
  );

  async function share(usePolish: boolean) {
    if (!weeklySummary) return;
    setError(null);
    setSuccess(null);
    trackEvent(token, 'share_clicked', { week_start_date: weeklySummary.week_start_date, use_polish: usePolish });
    try {
      if (usePolish) {
        setPolishing(true);
      } else {
        setSharing(true);
      }
      const content = usePolish ? await polishCommunityPost(token, defaultContent) : defaultContent;
      await createCommunityPost(token, {
        is_anonymous: true,
        mood: 'neutral',
        content: (content || defaultContent).slice(0, 800),
        tags: ['坚持打卡'],
        nutrition_snapshot: snapshot,
      });
      setSuccess('已分享本周复盘到社区');
      trackEvent(token, 'share_succeeded', { week_start_date: weeklySummary.week_start_date, use_polish: usePolish });
      await onShared?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : '分享失败，请稍后重试');
    } finally {
      setSharing(false);
      setPolishing(false);
    }
  }

  if (!weeklySummary) {
    return (
      <div className="rounded-3xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-5 shadow-sm">
        <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">分享即复盘</div>
        <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
          暂无本周统计数据，记录一些饮食后再来分享吧。
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-3xl border border-emerald-200/70 dark:border-emerald-900/40 bg-gradient-to-br from-emerald-50/70 via-white to-amber-50/30 dark:from-slate-900 dark:via-slate-900 dark:to-slate-800 p-5 shadow-sm transition-all duration-200 hover:shadow-md">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full border border-emerald-200 bg-emerald-100/70 px-3 py-1 text-xs font-medium text-emerald-800 dark:border-emerald-800/60 dark:bg-emerald-900/30 dark:text-emerald-200">
            <Send className="h-3.5 w-3.5" />
            分享即复盘
          </div>
          <div className="mt-3 text-sm text-gray-800 dark:text-gray-200">
            一键把本周营养摘要分享到社区，获得反馈与支持。
          </div>
          <pre className="mt-3 whitespace-pre-wrap rounded-2xl border border-emerald-100 bg-white/80 p-4 text-xs text-gray-700 dark:border-emerald-900/40 dark:bg-gray-900/50 dark:text-gray-200">
            {defaultContent}
          </pre>
        </div>

        <div className="flex flex-col items-end gap-2 shrink-0">
          <button
            type="button"
            onClick={() => share(false)}
            disabled={sharing || polishing}
            className="inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-3 py-2 text-xs font-semibold text-white hover:bg-emerald-700 disabled:opacity-70"
          >
            {sharing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            分享本周
          </button>
          <button
            type="button"
            onClick={() => share(true)}
            disabled={sharing || polishing}
            className="inline-flex items-center gap-2 rounded-xl border border-emerald-200 bg-white px-3 py-2 text-xs font-semibold text-emerald-700 hover:bg-emerald-50 disabled:opacity-70 dark:border-emerald-900/40 dark:bg-gray-900 dark:text-emerald-200 dark:hover:bg-emerald-900/20"
          >
            {polishing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
            AI 润色后分享
          </button>
        </div>
      </div>

      {(error || success) && (
        <div
          className={`mt-4 rounded-2xl border px-4 py-3 text-sm ${
            error
              ? 'border-red-200 bg-red-50 text-red-700 dark:border-red-900/60 dark:bg-red-900/20 dark:text-red-200'
              : 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/60 dark:bg-emerald-900/20 dark:text-emerald-200'
          }`}
          role={error ? 'alert' : 'status'}
        >
          {error || success}
        </div>
      )}
    </div>
  );
}

