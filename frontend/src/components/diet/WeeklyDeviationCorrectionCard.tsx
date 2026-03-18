import { useCallback, useEffect, useMemo, useState } from 'react';
import { CalendarDays, Loader2, RefreshCcw, Sparkles, Wand2 } from 'lucide-react';

import { applyReplan, getReplanPreview } from '../../services/api/diet';
import type { DietPlanMeal, DietReplanPreview, WeeklySummary } from '../../types/diet';
import { trackEvent } from '../../services/api/events';

const MEAL_LABELS: Record<string, string> = {
  breakfast: '早餐',
  lunch: '午餐',
  dinner: '晚餐',
  snack: '加餐',
};

function buildSummary(preview: DietReplanPreview | null, weeklySummary: WeeklySummary | null): string {
  if (!preview) return '正在生成未来 3-5 天的滚动重规划预览。';

  const deviation = Number(preview.before_summary?.total_deviation ?? 0);
  const affectedDays = preview.affected_days.length;
  const mealCount = preview.meal_changes.length;
  const totalCalories = weeklySummary?.total_calories;
  const shift = Number(preview.after_summary?.applied_shift ?? 0);

  const base = typeof totalCalories === 'number' ? `本周已记录 ${totalCalories.toFixed(0)} kcal。` : '';
  const deviationText =
    deviation === 0
      ? '当前偏差较小，以下预览以稳态优化为主。'
      : deviation > 0
        ? `本周累计超出约 ${Math.abs(deviation)} kcal，系统将把压力平滑分散到后续餐次。`
        : `本周累计低于计划约 ${Math.abs(deviation)} kcal，系统将温和补回后续餐次。`;
  const shiftText =
    mealCount > 0
      ? `预计影响 ${affectedDays} 天、${mealCount} 餐，总调整 ${shift >= 0 ? '+' : ''}${shift} kcal。`
      : '当前没有可安全调整的未来餐次。';
  const compensationText =
    preview.compensation_summary && preview.compensation_suggestions?.length
      ? '饮食修正空间不足，已补充轻量训练建议。'
      : '';

  return `${base}${deviationText}${shiftText}${compensationText}`;
}

function formatMealChange(change: DietReplanPreview['meal_changes'][number]): string {
  const mealLabel = MEAL_LABELS[change.meal_type] || change.meal_type;
  const fromCalories = change.old_total_calories ?? '--';
  const toCalories = change.new_total_calories ?? '--';
  return `${change.plan_date} · ${mealLabel} · ${fromCalories} → ${toCalories} kcal`;
}

export function WeeklyDeviationCorrectionCard({
  token,
  weekStartDate,
  weeklySummary,
  onApplied,
}: {
  token: string;
  weekStartDate: string;
  planMeals?: DietPlanMeal[];
  weeklySummary: WeeklySummary | null;
  onApplied?: () => void | Promise<void>;
}) {
  const [preview, setPreview] = useState<DietReplanPreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [appliedMessage, setAppliedMessage] = useState<string | null>(null);

  const summaryText = useMemo(
    () => buildSummary(preview, weeklySummary),
    [preview, weeklySummary]
  );

  const loadPreview = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    setAppliedMessage(null);
    try {
      const res = await getReplanPreview(token, weekStartDate);
      setPreview(res);
      trackEvent(token, 'diet_replan_preview_viewed', {
        week_start_date: weekStartDate,
        affected_days: res.affected_days.length,
        meal_count: res.meal_changes.length,
        write_conflicts: res.write_conflicts.length,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载滚动重规划失败');
    } finally {
      setLoading(false);
    }
  }, [token, weekStartDate]);

  useEffect(() => {
    void loadPreview();
  }, [loadPreview]);

  const applyRollingReplan = useCallback(async () => {
    if (!token || !preview) return;
    setApplying(true);
    setError(null);
    setAppliedMessage(null);
    try {
      const result = await applyReplan(token, preview.meal_changes);
      const appliedCount = Number(result.applied_count ?? 0);
      const conflictCount = result.write_conflicts.length;
      setAppliedMessage(
        conflictCount > 0
          ? `已更新 ${appliedCount} 个餐次，另有 ${conflictCount} 个餐次因冲突被跳过。`
          : `已更新 ${appliedCount} 个未来餐次。`
      );
      trackEvent(token, 'diet_replan_applied', {
        week_start_date: weekStartDate,
        applied_count: appliedCount,
        write_conflicts: conflictCount,
      });
      await onApplied?.();
      await loadPreview();
    } catch (err) {
      setError(err instanceof Error ? err.message : '应用滚动重规划失败');
    } finally {
      setApplying(false);
    }
  }, [loadPreview, onApplied, preview, token, weekStartDate]);

  const canApply = Boolean(token && preview && preview.meal_changes.length > 0 && !loading && !applying);

  return (
    <div className="rounded-3xl border border-violet-200/70 dark:border-violet-900/40 bg-gradient-to-br from-violet-50 via-white to-amber-50/40 dark:from-slate-900 dark:via-slate-900 dark:to-slate-800 p-5 shadow-sm transition-all duration-200 hover:shadow-md">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full border border-violet-200 bg-violet-100/70 px-3 py-1 text-xs font-medium text-violet-800 dark:border-violet-800/60 dark:bg-violet-900/30 dark:text-violet-200">
            <Sparkles className="h-3.5 w-3.5" />
            七天滚动重规划
          </div>
          <div className="mt-3 text-sm text-gray-800 dark:text-gray-200">
            {summaryText}
          </div>
        </div>

        <div className="flex flex-col items-end gap-2 shrink-0">
          <button
            type="button"
            onClick={() => void loadPreview()}
            disabled={loading || applying}
            className="inline-flex items-center gap-2 rounded-xl border border-gray-200 bg-white px-3 py-2 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-70 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200 dark:hover:bg-gray-800"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCcw className="h-4 w-4" />}
            刷新预览
          </button>
          <button
            type="button"
            onClick={() => void applyRollingReplan()}
            disabled={!canApply}
            className="inline-flex items-center gap-2 rounded-xl bg-violet-500 px-3 py-2 text-xs font-semibold text-white hover:bg-violet-600 disabled:opacity-70"
          >
            {applying ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wand2 className="h-4 w-4" />}
            写回未来餐次
          </button>
        </div>
      </div>

      <div className="mt-4 rounded-2xl border border-violet-200/70 bg-white/80 p-4 text-xs text-gray-700 dark:border-violet-900/40 dark:bg-gray-900/50 dark:text-gray-200">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="font-semibold text-violet-800 dark:text-violet-200">预览结果</div>
            <div className="mt-2 text-sm font-semibold text-gray-900 dark:text-gray-100">
              未来 {preview?.affected_days.length ?? 0} 天 · {preview?.meal_changes.length ?? 0} 个餐次待调整
            </div>
          </div>
          <div className="inline-flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-[11px] text-amber-700 dark:border-amber-900/40 dark:bg-amber-500/10 dark:text-amber-200">
            <CalendarDays className="h-3.5 w-3.5" />
            冲突 {preview?.write_conflicts.length ?? 0} 个
          </div>
        </div>

        <div className="mt-3 grid gap-3 lg:grid-cols-2">
          <div className="rounded-2xl border border-gray-100 bg-gray-50/80 px-3 py-3 dark:border-gray-800 dark:bg-gray-950/40">
            <div className="text-[11px] font-medium text-gray-500">重规划餐次</div>
            <div className="mt-2 space-y-2">
              {preview?.meal_changes.length ? (
                preview.meal_changes.slice(0, 4).map((change) => (
                  <div
                    key={change.meal_id}
                    className="rounded-xl bg-white/80 px-3 py-2 text-[12px] text-gray-700 dark:bg-gray-900 dark:text-gray-200"
                  >
                    <div className="font-medium">{formatMealChange(change)}</div>
                    <div className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
                      变化 {change.delta_calories && change.delta_calories > 0 ? '+' : ''}
                      {change.delta_calories ?? 0} kcal
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-[12px] text-gray-500 dark:text-gray-400">
                  当前没有可安全调整的未来餐次。
                </div>
              )}
            </div>
          </div>

          <div className="rounded-2xl border border-gray-100 bg-gray-50/80 px-3 py-3 dark:border-gray-800 dark:bg-gray-950/40">
            <div className="text-[11px] font-medium text-gray-500">跳过原因</div>
            <div className="mt-2 space-y-2">
              {preview?.write_conflicts.length ? (
                preview.write_conflicts.slice(0, 4).map((conflict, index) => (
                  <div
                    key={`${conflict.plan_date}-${conflict.meal_type}-${index}`}
                    className="rounded-xl bg-white/80 px-3 py-2 text-[12px] text-gray-700 dark:bg-gray-900 dark:text-gray-200"
                  >
                    <div className="font-medium">
                      {conflict.plan_date} · {MEAL_LABELS[conflict.meal_type || ''] || conflict.meal_type}
                    </div>
                    <div className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">{conflict.reason}</div>
                  </div>
                ))
              ) : (
                <div className="text-[12px] text-gray-500 dark:text-gray-400">
                  当前没有冲突，可直接写回。
                </div>
              )}
            </div>
          </div>
        </div>

        {preview?.compensation_suggestions?.length ? (
          <div className="mt-3 rounded-2xl border border-emerald-200/70 bg-emerald-50/70 px-3 py-3 dark:border-emerald-900/40 dark:bg-emerald-900/10">
            <div className="text-[11px] font-medium text-emerald-700 dark:text-emerald-200">
              训练 / 运动补偿建议
            </div>
            {preview.compensation_summary ? (
              <div className="mt-2 text-[12px] text-emerald-800/90 dark:text-emerald-100/90">
                {preview.compensation_summary}
              </div>
            ) : null}
            <div className="mt-3 grid gap-2 md:grid-cols-2">
              {preview.compensation_suggestions.map((item) => (
                <div
                  key={`${item.title}-${item.minutes}`}
                  className="rounded-xl bg-white/80 px-3 py-2 text-[12px] text-gray-700 dark:bg-gray-900 dark:text-gray-200"
                >
                  <div className="font-medium">
                    {item.title} · {item.minutes} 分钟
                  </div>
                  <div className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
                    预计消耗约 {item.estimated_kcal_burn} kcal · 强度 {item.intensity}
                  </div>
                  <div className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">{item.reason}</div>
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </div>

      {(error || appliedMessage) && (
        <div
          className={`mt-4 rounded-2xl border px-4 py-3 text-sm ${
            error
              ? 'border-red-200 bg-red-50 text-red-700 dark:border-red-900/60 dark:bg-red-900/20 dark:text-red-200'
              : 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/60 dark:bg-emerald-900/20 dark:text-emerald-200'
          }`}
          role={error ? 'alert' : 'status'}
        >
          {error || appliedMessage}
        </div>
      )}
    </div>
  );
}
