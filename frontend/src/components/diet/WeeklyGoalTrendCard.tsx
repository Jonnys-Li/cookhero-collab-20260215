import { Activity, Flag, LineChart as LineChartIcon, ShieldPlus } from 'lucide-react';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import type { WeeklySummary, WeeklyBudgetTimelineEntry } from '../../types/diet';

const GOAL_SOURCE_LABELS: Record<string, string> = {
  explicit: '用户目标',
  avg7d: '近 7 天均值',
  default1800: '系统默认 1800',
  tdee_estimate: 'TDEE 估算',
};

interface TrendRow {
  date: string;
  label: string;
  actualCalories: number | null;
  targetCalories: number | null;
  deviationCalories: number | null;
  goalSourceLabel: string | null;
  goalSourceChanged: boolean;
  emotionExemptionActive: boolean;
}

function formatShortLabel(dateStr: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dateStr);
  if (!match) return dateStr;
  return `${Number(match[2])}/${Number(match[3])}`;
}

function formatGoalSourceLabel(goalSource: string | null | undefined): string | null {
  if (!goalSource) return null;
  return GOAL_SOURCE_LABELS[goalSource] || goalSource;
}

function toNumberOrNull(value: unknown): number | null {
  if (typeof value !== 'number' || Number.isNaN(value)) return null;
  return value;
}

function buildTrendRows(summary: WeeklySummary | null): TrendRow[] {
  if (!summary?.daily_budget_timeline?.length) return [];
  return summary.daily_budget_timeline.map((entry: WeeklyBudgetTimelineEntry, index: number) => {
    const actualValue = summary.daily_data?.[entry.date]?.calories;
    const actualCalories = toNumberOrNull(actualValue);
    const targetCalories = toNumberOrNull(entry.effective_goal);
    const deviationCalories =
      actualCalories !== null && targetCalories !== null ? actualCalories - targetCalories : null;
    const goalSourceLabel = formatGoalSourceLabel(entry.goal_source);
    const prevGoalSource = index > 0 ? summary.daily_budget_timeline?.[index - 1]?.goal_source : null;
    const goalSourceChanged = index > 0 && entry.goal_source !== prevGoalSource;
    const emotionExemptionActive = Boolean(
      entry.emotion_exemption?.active ?? entry.emotion_exemption?.is_active
    );

    return {
      date: entry.date,
      label: formatShortLabel(entry.date),
      actualCalories,
      targetCalories,
      deviationCalories,
      goalSourceLabel,
      goalSourceChanged,
      emotionExemptionActive,
    };
  });
}

function tooltipValue(value: number | null): string {
  return value === null ? '--' : `${Math.round(value)} kcal`;
}

export function WeeklyGoalTrendCard({
  weeklySummary,
}: {
  weeklySummary: WeeklySummary | null;
}) {
  const rows = buildTrendRows(weeklySummary);
  if (!rows.length) return null;

  return (
    <div className="rounded-3xl border border-sky-200/70 dark:border-sky-900/40 bg-gradient-to-br from-sky-50 via-white to-emerald-50/40 dark:from-slate-900 dark:via-slate-900 dark:to-slate-800 p-5 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full border border-sky-200 bg-sky-100/70 px-3 py-1 text-xs font-medium text-sky-800 dark:border-sky-800/60 dark:bg-sky-900/30 dark:text-sky-200">
            <LineChartIcon className="h-3.5 w-3.5" />
            周趋势视图
          </div>
          <div className="mt-3 text-sm text-gray-800 dark:text-gray-200">
            同时查看每日摄入、基线目标和当日偏差，并标出情绪保护期与目标来源变化。
          </div>
        </div>
        <div className="text-right text-xs text-gray-500 dark:text-gray-400">
          <div>周目标 {weeklySummary?.weekly_goal_calories ?? '--'} kcal</div>
          <div className="mt-1">
            周差值{' '}
            {weeklySummary?.weekly_goal_gap === null || weeklySummary?.weekly_goal_gap === undefined
              ? '--'
              : `${weeklySummary.weekly_goal_gap >= 0 ? '+' : ''}${weeklySummary.weekly_goal_gap} kcal`}
          </div>
        </div>
      </div>

      <div className="mt-4 h-[280px] rounded-2xl border border-sky-100/70 bg-white/80 p-3 dark:border-sky-900/30 dark:bg-gray-950/40">
        <div className="mb-3 flex flex-wrap gap-2 text-[11px] text-gray-600 dark:text-gray-300">
          <span className="inline-flex items-center gap-1 rounded-full bg-orange-50 px-2 py-1 text-orange-700 dark:bg-orange-900/20 dark:text-orange-200">
            <span className="h-2 w-2 rounded-full bg-orange-500" />
            实际摄入
          </span>
          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-1 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-200">
            <span className="h-2 w-2 rounded-full bg-emerald-500" />
            基线目标
          </span>
          <span className="inline-flex items-center gap-1 rounded-full bg-blue-50 px-2 py-1 text-blue-700 dark:bg-blue-900/20 dark:text-blue-200">
            <span className="h-2 w-2 rounded-full bg-blue-600" />
            当日偏差
          </span>
        </div>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 12, right: 16, left: -12, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#dbeafe" />
            <XAxis dataKey="label" tick={{ fontSize: 12 }} stroke="#64748b" />
            <YAxis tick={{ fontSize: 12 }} stroke="#64748b" />
            <YAxis yAxisId="deviation" orientation="right" tick={{ fontSize: 12 }} stroke="#94a3b8" />
            <Tooltip
              formatter={(value: number | string | undefined, name: string | undefined) => {
                if (name === 'goalSourceLabel') return [String(value ?? '--'), '基线来源'];
                return [tooltipValue(typeof value === 'number' ? value : null), String(name ?? '--')];
              }}
              contentStyle={{
                borderRadius: '16px',
                borderColor: '#bfdbfe',
                backgroundColor: 'rgba(255,255,255,0.96)',
              }}
              labelFormatter={(label: string, payload) => {
                const row = payload?.[0]?.payload as TrendRow | undefined;
                if (!row) return label;
                const badges = [
                  row.goalSourceLabel ? `来源 ${row.goalSourceLabel}` : null,
                  row.emotionExemptionActive ? '情绪保护期' : null,
                  row.goalSourceChanged ? '来源切换' : null,
                ].filter(Boolean);
                return badges.length ? `${row.date} · ${badges.join(' · ')}` : row.date;
              }}
            />
            <Legend />
            <ReferenceLine yAxisId="deviation" y={0} stroke="#cbd5e1" strokeDasharray="4 4" />
            <Line
              type="monotone"
              dataKey="actualCalories"
              name="实际摄入"
              stroke="#f97316"
              strokeWidth={2.5}
              dot={{ r: 3 }}
              connectNulls
            />
            <Line
              type="monotone"
              dataKey="targetCalories"
              name="基线目标"
              stroke="#10b981"
              strokeWidth={2.5}
              dot={{ r: 3 }}
              connectNulls
            />
            <Line
              type="monotone"
              yAxisId="deviation"
              dataKey="deviationCalories"
              name="当日偏差"
              stroke="#2563eb"
              strokeWidth={2}
              dot={{ r: 3 }}
              connectNulls
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-7">
        {rows.map((row) => (
          <div
            key={row.date}
            className="rounded-2xl border border-gray-100 bg-white/80 px-3 py-3 text-[12px] text-gray-700 dark:border-gray-800 dark:bg-gray-950/40 dark:text-gray-200"
          >
            <div className="font-medium text-gray-900 dark:text-gray-100">{row.label}</div>
            <div className="mt-2 space-y-1 text-[11px] text-gray-500 dark:text-gray-400">
              <div>摄入 {tooltipValue(row.actualCalories)}</div>
              <div>目标 {tooltipValue(row.targetCalories)}</div>
              <div>
                偏差{' '}
                {row.deviationCalories === null
                  ? '--'
                  : `${row.deviationCalories >= 0 ? '+' : ''}${Math.round(row.deviationCalories)} kcal`}
              </div>
            </div>

            <div className="mt-3 flex flex-wrap gap-1.5">
              {row.goalSourceLabel ? (
                <span className="inline-flex items-center gap-1 rounded-full bg-sky-50 px-2 py-1 text-[10px] text-sky-700 dark:bg-sky-900/20 dark:text-sky-200">
                  <Activity className="h-3 w-3" />
                  {row.goalSourceLabel}
                </span>
              ) : null}
              {row.emotionExemptionActive ? (
                <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-1 text-[10px] text-amber-700 dark:bg-amber-900/20 dark:text-amber-200">
                  <ShieldPlus className="h-3 w-3" />
                  情绪保护期
                </span>
              ) : null}
              {row.goalSourceChanged ? (
                <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-1 text-[10px] text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-200">
                  <Flag className="h-3 w-3" />
                  来源切换
                </span>
              ) : null}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
