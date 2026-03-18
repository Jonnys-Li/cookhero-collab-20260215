import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import type { DietBudgetSnapshot, WeeklySummary } from '../../types/diet';

type TrendRow = {
  date: string;
  label: string;
  calories: number;
  goal: number | null;
  delta: number | null;
  goalSource: string;
  exemptionActive: boolean;
  specialMark: string | null;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function readNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  return null;
}

function formatDayLabel(date: string): string {
  const parsed = new Date(`${date}T00:00:00`);
  return `${parsed.getMonth() + 1}/${parsed.getDate()}`;
}

function goalSourceLabel(source: string | null | undefined): string {
  if (source === 'explicit') return '手动';
  if (source === 'tdee_estimate') return '代谢';
  if (source === 'avg7d') return 'avg7d';
  if (source === 'default1800') return '默认';
  return source || '未标注';
}

function buildTrendRows(
  summary: WeeklySummary | null,
  budgetSnapshot: DietBudgetSnapshot | null
): TrendRow[] {
  if (!summary?.daily_data) return [];
  const summaryRecord = summary as unknown as Record<string, unknown>;
  const dailyGoalTimeline = Array.isArray(summaryRecord.daily_goal_timeline)
    ? summaryRecord.daily_goal_timeline
    : [];
  const goalSourceTimeline = Array.isArray(summaryRecord.goal_source_timeline)
    ? summaryRecord.goal_source_timeline
    : [];
  const exemptionTimeline = Array.isArray(summaryRecord.emotion_exemption_timeline)
    ? summaryRecord.emotion_exemption_timeline
    : [];

  const baseGoal = readNumber(summaryRecord.base_goal) ?? budgetSnapshot?.base_goal ?? null;
  const effectiveGoal =
    readNumber(summaryRecord.effective_goal) ?? budgetSnapshot?.effective_goal ?? baseGoal;
  const activeSource =
    (typeof summaryRecord.goal_source === 'string' ? summaryRecord.goal_source : null) ||
    budgetSnapshot?.goal_source ||
    null;
  const todayBudgetDate = budgetSnapshot?.date || summary.today_budget?.date || null;
  const emotionActive = Boolean(
    budgetSnapshot?.emotion_exemption?.active ??
      budgetSnapshot?.emotion_exemption?.is_active ??
      summary.emotion_exemption?.active ??
      summary.emotion_exemption?.is_active
  );

  return Object.entries(summary.daily_data).map(([date, day]) => {
    const goalEntry = dailyGoalTimeline.find(
      (item) => isRecord(item) && String(item.date || '') === date
    ) as Record<string, unknown> | undefined;
    const sourceEntry = goalSourceTimeline.find(
      (item) => isRecord(item) && String(item.date || '') === date
    ) as Record<string, unknown> | undefined;
    const exemptionEntry = exemptionTimeline.find(
      (item) => isRecord(item) && String(item.date || '') === date
    ) as Record<string, unknown> | undefined;

    const goal =
      readNumber(goalEntry?.effective_goal) ??
      readNumber(goalEntry?.goal) ??
      (todayBudgetDate === date ? effectiveGoal : baseGoal);
    const calories = typeof day.calories === 'number' ? day.calories : 0;
    const exemptionForDay =
      Boolean(exemptionEntry?.active ?? exemptionEntry?.is_active) ||
      (emotionActive && todayBudgetDate === date);
    const specialMark =
      (typeof exemptionEntry?.summary === 'string' && exemptionEntry.summary) ||
      (exemptionForDay ? '豁免' : null);

    return {
      date,
      label: formatDayLabel(date),
      calories,
      goal,
      delta: goal === null ? null : calories - goal,
      goalSource:
        (typeof sourceEntry?.goal_source === 'string' && sourceEntry.goal_source) || activeSource || 'unknown',
      exemptionActive: exemptionForDay,
      specialMark,
    };
  });
}

function deltaLabel(delta: number | null): string {
  if (delta === null) return '偏差 --';
  const prefix = delta > 0 ? '+' : '';
  return `偏差 ${prefix}${Math.round(delta)} kcal`;
}

export function WeeklyDefenseTrendCard({
  summary,
  budgetSnapshot,
}: {
  summary: WeeklySummary | null;
  budgetSnapshot: DietBudgetSnapshot | null;
}) {
  const rows = buildTrendRows(summary, budgetSnapshot);
  const weeklyGoalGap = (() => {
    const summaryRecord = (summary || {}) as Record<string, unknown>;
    const value = readNumber(summaryRecord.weekly_goal_gap);
    if (value === null) return null;
    return Math.round(value);
  })();

  if (!rows.length) return null;

  return (
    <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-5 shadow-sm transition-all duration-200 hover:shadow-md">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">一周趋势总览</h3>
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            把每天吃了多少、目标是多少、差多少放在一张图里，并标出情绪保护期和目标来源。
          </p>
        </div>
        <div className="rounded-full border border-gray-200 bg-gray-50 px-3 py-1 text-xs font-medium text-gray-700 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200">
          周偏差 {weeklyGoalGap === null ? '--' : `${weeklyGoalGap >= 0 ? '+' : ''}${weeklyGoalGap} kcal`}
        </div>
      </div>

      <div className="mt-4 h-[280px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={rows} margin={{ top: 16, right: 16, left: -12, bottom: 4 }}>
            <defs>
              <linearGradient id="defenseCalories" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#f59e0b" stopOpacity={0.35} />
                <stop offset="100%" stopColor="#f59e0b" stopOpacity={0.04} />
              </linearGradient>
              <linearGradient id="defenseGoal" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#10b981" stopOpacity={0.25} />
                <stop offset="100%" stopColor="#10b981" stopOpacity={0.03} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.25} />
            <XAxis dataKey="label" tickLine={false} axisLine={false} fontSize={12} />
            <YAxis tickLine={false} axisLine={false} width={42} fontSize={12} />
            <Tooltip
              formatter={(value: unknown, name: string | number | undefined) => {
                const numericValue =
                  typeof value === 'number' && Number.isFinite(value) ? value : null;
                return [
                  numericValue === null ? '--' : `${Math.round(numericValue)} kcal`,
                  name === 'calories' ? '实际摄入' : '目标线',
                ];
              }}
              labelFormatter={(label) => `日期 ${label}`}
              contentStyle={{
                borderRadius: 16,
                border: '1px solid rgba(229, 231, 235, 0.8)',
                background: 'rgba(255,255,255,0.96)',
              }}
            />
            <Area
              type="monotone"
              dataKey="goal"
              stroke="#10b981"
              fill="url(#defenseGoal)"
              strokeWidth={2}
              activeDot={{ r: 4 }}
            />
            <Area
              type="monotone"
              dataKey="calories"
              stroke="#f59e0b"
              fill="url(#defenseCalories)"
              strokeWidth={2}
              activeDot={{ r: 4 }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      <div className="mt-4 grid grid-cols-1 md:grid-cols-7 gap-2">
        {rows.map((row) => (
          <div
            key={row.date}
            className="rounded-2xl border border-gray-100 dark:border-gray-800 bg-gray-50/70 dark:bg-gray-950/30 px-3 py-3"
          >
            <div className="flex items-center justify-between gap-2">
              <div className="text-xs font-medium text-gray-700 dark:text-gray-200">{row.label}</div>
              <div className="text-[10px] text-gray-500 dark:text-gray-400">{goalSourceLabel(row.goalSource)}</div>
            </div>
            <div className="mt-2 text-sm font-semibold text-gray-900 dark:text-gray-100">
              {Math.round(row.calories)} kcal
            </div>
            <div className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
              目标 {row.goal === null ? '--' : Math.round(row.goal)} kcal
            </div>
            <div
              className={`mt-1 text-[11px] ${
                row.delta === null
                  ? 'text-gray-500 dark:text-gray-400'
                  : row.delta > 0
                    ? 'text-rose-600 dark:text-rose-300'
                    : 'text-emerald-600 dark:text-emerald-300'
              }`}
            >
              {deltaLabel(row.delta)}
            </div>
            {row.exemptionActive || row.specialMark ? (
              <div className="mt-2 inline-flex rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] font-medium text-amber-700 dark:border-amber-900/40 dark:bg-amber-900/20 dark:text-amber-200">
                {row.specialMark || '特殊标记'}
              </div>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}
