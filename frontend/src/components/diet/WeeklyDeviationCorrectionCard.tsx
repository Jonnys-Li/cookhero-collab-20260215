import { useCallback, useMemo, useState } from 'react';
import { Loader2, Sparkles, Wand2 } from 'lucide-react';

import { addMealToPlan, getDeviationAnalysis } from '../../services/api/diet';
import type { DeviationAnalysis, DietPlanMeal, WeeklySummary } from '../../types/diet';
import { trackEvent } from '../../services/api/events';

type MealType = 'breakfast' | 'lunch' | 'dinner' | 'snack';

const MEAL_ORDER: MealType[] = ['breakfast', 'lunch', 'dinner', 'snack'];
const MEAL_LABELS: Record<MealType, string> = {
  breakfast: '早餐',
  lunch: '午餐',
  dinner: '晚餐',
  snack: '加餐',
};

function startOfLocalDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

function formatDateYMD(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  const d = startOfLocalDay(date);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function isSameYmd(date: Date, ymd: string): boolean {
  return formatDateYMD(date) === ymd;
}

function pickNextMealType(now: Date): MealType {
  const hour = now.getHours();
  if (hour < 10) return 'breakfast';
  if (hour < 14) return 'lunch';
  if (hour < 20) return 'dinner';
  return 'snack';
}

function hasPlanMeal(
  meals: DietPlanMeal[] | undefined,
  planDate: string,
  mealType: MealType
): boolean {
  return Boolean(meals?.some((m) => m.plan_date === planDate && m.meal_type === mealType));
}

function findNextEmptySlot(
  meals: DietPlanMeal[] | undefined,
  startDate: Date,
  dayWindow: number
): { planDate: string; mealType: MealType } | null {
  const start = startOfLocalDay(startDate);
  const startMealType = pickNextMealType(startDate);
  for (let dayOffset = 0; dayOffset <= dayWindow; dayOffset++) {
    const date = new Date(start);
    date.setDate(start.getDate() + dayOffset);
    const planDate = formatDateYMD(date);
    const mealTypes =
      dayOffset === 0
        ? MEAL_ORDER.slice(MEAL_ORDER.indexOf(startMealType))
        : MEAL_ORDER;
    for (const mealType of mealTypes) {
      if (!hasPlanMeal(meals, planDate, mealType)) {
        return { planDate, mealType };
      }
    }
  }
  return null;
}

function buildDeviationSummary(
  analysis: DeviationAnalysis | null,
  weeklySummary: WeeklySummary | null
): string {
  if (!analysis) return '点击生成本周偏差总结与下一餐纠偏建议。';
  if (!analysis.has_plan) {
    return analysis.message || '本周暂无计划餐次，先添加计划再来纠偏会更有效。';
  }
  const executionRate =
    typeof analysis.execution_rate === 'number' ? analysis.execution_rate : null;
  const deviation =
    typeof analysis.total_deviation === 'number' ? analysis.total_deviation : null;
  const deviationPct =
    typeof analysis.total_deviation_pct === 'number' ? analysis.total_deviation_pct : null;
  const calories = weeklySummary?.total_calories;

  const deviationText = (() => {
    if (deviation === null) return '热量偏差 -- kcal';
    const sign = deviation >= 0 ? '+' : '';
    const absText = Math.abs(deviation).toFixed(0);
    const pctText =
      deviationPct === null ? '' : `（${deviationPct >= 0 ? '+' : ''}${deviationPct.toFixed(0)}%）`;
    return `热量偏差 ${sign}${absText} kcal${pctText}`;
  })();

  const execText =
    executionRate === null ? '执行率 --%' : `执行率 ${executionRate.toFixed(0)}%`;
  const baseText =
    typeof calories === 'number' ? `本周已记录 ${calories.toFixed(0)} kcal。` : '';

  return `${baseText}${execText}，${deviationText}。`;
}

function suggestedCorrectionDish(deviation: number | null): {
  name: string;
  calories?: number;
  protein?: number;
  fat?: number;
  carbs?: number;
} {
  if (deviation === null) {
    return {
      name: '稳态餐：时蔬蛋白碗',
      calories: 520,
      protein: 32,
      fat: 18,
      carbs: 55,
    };
  }

  if (deviation > 200) {
    return {
      name: '清爽纠偏：鸡胸肉蔬菜沙拉',
      calories: 420,
      protein: 38,
      fat: 14,
      carbs: 28,
    };
  }

  if (deviation < -200) {
    return {
      name: '能量补充：酸奶燕麦坚果',
      calories: 360,
      protein: 20,
      fat: 12,
      carbs: 44,
    };
  }

  return {
    name: '保持节奏：番茄鸡蛋 + 时蔬',
    calories: 480,
    protein: 28,
    fat: 16,
    carbs: 55,
  };
}

export function WeeklyDeviationCorrectionCard({
  token,
  weekStartDate,
  planMeals,
  weeklySummary,
  onApplied,
}: {
  token: string;
  weekStartDate: string;
  planMeals?: DietPlanMeal[];
  weeklySummary: WeeklySummary | null;
  onApplied?: () => void | Promise<void>;
}) {
  const [analysis, setAnalysis] = useState<DeviationAnalysis | null>(null);
  const [loading, setLoading] = useState(false);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [appliedMessage, setAppliedMessage] = useState<string | null>(null);

  const summaryText = useMemo(
    () => buildDeviationSummary(analysis, weeklySummary),
    [analysis, weeklySummary]
  );

  const deviationValue =
    analysis && typeof analysis.total_deviation === 'number' ? analysis.total_deviation : null;
  const suggestion = useMemo(() => suggestedCorrectionDish(deviationValue), [deviationValue]);

  const loadDeviation = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    setAppliedMessage(null);
    try {
      const res = await getDeviationAnalysis(token, weekStartDate);
      setAnalysis(res);
      trackEvent(token, 'deviation_viewed', { week_start_date: weekStartDate });
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载偏差分析失败');
    } finally {
      setLoading(false);
    }
  }, [token, weekStartDate]);

  const applyCorrection = useCallback(async () => {
    if (!token) return;
    if (!analysis) {
      await loadDeviation();
      return;
    }
    if (!analysis.has_plan) {
      setError('本周暂无计划餐次，先添加计划后再应用纠偏会更有效。');
      return;
    }

    setApplying(true);
    setError(null);
    setAppliedMessage(null);
    try {
      const now = new Date();
      const weekStart = new Date(`${weekStartDate}T00:00:00`);
      const baseDate = isSameYmd(now, weekStartDate) || now >= weekStart ? now : weekStart;

      const slot =
        findNextEmptySlot(planMeals, baseDate, 2) ||
        findNextEmptySlot(planMeals, new Date(), 6) ||
        findNextEmptySlot(planMeals, weekStart, 6);

      if (!slot) {
        setError('未找到可写入的空餐次位置，请手动添加。');
        return;
      }

      await addMealToPlan(token, {
        plan_date: slot.planDate,
        meal_type: slot.mealType,
        dishes: [
          {
            name: suggestion.name,
            calories: suggestion.calories,
            protein: suggestion.protein,
            fat: suggestion.fat,
            carbs: suggestion.carbs,
          },
        ],
        notes: `自动纠偏建议：根据本周偏差生成（week_start=${weekStartDate}）。`,
      });

      setAppliedMessage(`已写入 ${slot.planDate} ${MEAL_LABELS[slot.mealType]} 的纠偏餐次`);
      trackEvent(token, 'correction_applied', {
        week_start_date: weekStartDate,
        plan_date: slot.planDate,
        meal_type: slot.mealType,
      });
      await onApplied?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : '应用纠偏失败');
    } finally {
      setApplying(false);
    }
  }, [analysis, loadDeviation, onApplied, planMeals, suggestion, token, weekStartDate]);

  const canApply = Boolean(token) && !loading && !applying;

  return (
    <div className="rounded-3xl border border-violet-200/70 dark:border-violet-900/40 bg-gradient-to-br from-violet-50 via-white to-amber-50/40 dark:from-slate-900 dark:via-slate-900 dark:to-slate-800 p-5 shadow-sm transition-all duration-200 hover:shadow-md">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full border border-violet-200 bg-violet-100/70 px-3 py-1 text-xs font-medium text-violet-800 dark:border-violet-800/60 dark:bg-violet-900/30 dark:text-violet-200">
            <Sparkles className="h-3.5 w-3.5" />
            本周偏差总结
          </div>
          <div className="mt-3 text-sm text-gray-800 dark:text-gray-200">
            {summaryText}
          </div>
          {analysis?.meal_deviations?.length ? (
            <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
              主要偏差餐次：{analysis.meal_deviations.slice(0, 2).map((m) => m.meal_key).join('、')}
            </div>
          ) : null}
        </div>

        <div className="flex flex-col items-end gap-2 shrink-0">
          <button
            type="button"
            onClick={loadDeviation}
            disabled={loading || applying}
            className="inline-flex items-center gap-2 rounded-xl border border-gray-200 bg-white px-3 py-2 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-70 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200 dark:hover:bg-gray-800"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wand2 className="h-4 w-4" />}
            生成纠偏建议
          </button>
          <button
            type="button"
            onClick={applyCorrection}
            disabled={!canApply}
            className="inline-flex items-center gap-2 rounded-xl bg-violet-500 px-3 py-2 text-xs font-semibold text-white hover:bg-violet-600 disabled:opacity-70"
          >
            {applying ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            一键写入下一餐
          </button>
        </div>
      </div>

      <div className="mt-4 rounded-2xl border border-violet-200/70 bg-white/80 p-4 text-xs text-gray-700 dark:border-violet-900/40 dark:bg-gray-900/50 dark:text-gray-200">
        <div className="font-semibold text-violet-800 dark:text-violet-200">建议预览</div>
        <div className="mt-2">
          {suggestion.name}
          {suggestion.calories ? ` · ${suggestion.calories} kcal` : ''}
          {suggestion.protein ? ` · P ${suggestion.protein}g` : ''}
          {suggestion.fat ? ` · F ${suggestion.fat}g` : ''}
          {suggestion.carbs ? ` · C ${suggestion.carbs}g` : ''}
        </div>
        <div className="mt-2 text-[11px] text-gray-500 dark:text-gray-400">
          说明：当前是前端 MVP 纠偏策略（无 LLM）。后续可由后端提供 SmartAction 生成更个性化的下一餐选项。
        </div>
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

      {/* TODO(backend): Prefer SmartAction correction flow once available.
          Option A: GET /api/v1/diet/corrections/next-meal?week_start_date=YYYY-MM-DD
          -> { action_id, session_id, next_meal_options: [...] }
          Then apply via POST /api/v1/agent/smart-actions/apply.
      */}
    </div>
  );
}

