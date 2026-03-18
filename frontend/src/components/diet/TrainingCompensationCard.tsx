import { Dumbbell, Footprints, HeartHandshake } from 'lucide-react';

import type { DietBudgetSnapshot, UserFoodPreference, WeeklySummary } from '../../types/diet';

type SuggestionTone = 'emerald' | 'amber' | 'sky';

type TrainingSuggestion = {
  title: string;
  description: string;
  focus: string;
  sourceLabel: string;
  tone: SuggestionTone;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function readNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  return null;
}

function readString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}

function extractBackendSuggestion(summary: WeeklySummary | null): TrainingSuggestion | null {
  if (!summary) return null;
  const summaryRecord = summary as unknown as Record<string, unknown>;
  const candidates = [
    summaryRecord.training_suggestion,
    summaryRecord.training_compensation_suggestion,
    isRecord(summaryRecord.goal_context) ? summaryRecord.goal_context.training_suggestion : null,
    isRecord(summaryRecord.goal_context)
      ? summaryRecord.goal_context.training_compensation_suggestion
      : null,
  ];

  for (const candidate of candidates) {
    if (typeof candidate === 'string' && candidate.trim()) {
      return {
        title: '训练/补偿建议',
        description: candidate.trim(),
        focus: '按后端 suggestion 展示，当前不增加额外交互。',
        sourceLabel: '后端 suggestion',
        tone: 'sky',
      };
    }
    if (!isRecord(candidate)) continue;
    const title = readString(candidate.title) || readString(candidate.headline) || '训练/补偿建议';
    const description =
      readString(candidate.description) ||
      readString(candidate.summary) ||
      readString(candidate.message);
    if (!description) continue;
    const focus =
      readString(candidate.focus) ||
      readString(candidate.action) ||
      readString(candidate.recovery_hint) ||
      '按后端 suggestion 展示，当前不增加额外交互。';
    return {
      title,
      description,
      focus,
      sourceLabel: readString(candidate.source_label) || '后端 suggestion',
      tone:
        readString(candidate.tone) === 'emerald' ||
        readString(candidate.tone) === 'amber' ||
        readString(candidate.tone) === 'sky'
          ? (readString(candidate.tone) as SuggestionTone)
          : 'sky',
    };
  }
  return null;
}

function buildFallbackSuggestion(
  summary: WeeklySummary | null,
  budgetSnapshot: DietBudgetSnapshot | null,
  preference: UserFoodPreference | null
): TrainingSuggestion {
  const summaryRecord = (summary || {}) as Record<string, unknown>;
  const weeklyGoalGap = readNumber(summaryRecord.weekly_goal_gap);
  const avgDailyGoalGap = readNumber(summaryRecord.avg_daily_goal_gap);
  const goalSource = readString(summaryRecord.goal_source) || budgetSnapshot?.goal_source || null;
  const emotionExemption = budgetSnapshot?.emotion_exemption || summary?.emotion_exemption;
  const emotionActive = Boolean(emotionExemption?.active ?? emotionExemption?.is_active);
  const estimate = preference?.metabolic_estimate;

  if (emotionActive) {
    return {
      title: '今天先稳住节奏，不做补偿训练',
      description:
        readString(emotionExemption?.summary) ||
        '当前处在情绪豁免或特殊支持状态，饮食与训练都优先以恢复稳定为主。',
      focus: '建议 10-20 分钟轻步行、舒缓拉伸或呼吸放松，不用额外追求“把热量练回来”。',
      sourceLabel: '基于情绪豁免状态',
      tone: 'amber',
    };
  }

  if ((weeklyGoalGap ?? 0) > 700 || (avgDailyGoalGap ?? 0) > 120) {
    return {
      title: '训练日可加一个轻补偿窗口',
      description:
        '本周摄入高于基线较明显，建议用轻中强度活动帮你把节奏拉回，而不是靠极端节食。',
      focus: '优先 20-30 分钟快走、单车或低冲击有氧；训练后下一餐保持蛋白 + 蔬菜即可。',
      sourceLabel: goalSource === 'tdee_estimate' ? '基于代谢画像目标' : '基于本周目标差',
      tone: 'emerald',
    };
  }

  if ((weeklyGoalGap ?? 0) < -700 || (avgDailyGoalGap ?? 0) < -120) {
    return {
      title: '训练后更该补能，不建议再做额外补偿',
      description:
        '这周整体摄入已经低于基线，继续叠加补偿训练容易把恢复和执行感一起拉低。',
      focus: `优先保证训练后补充蛋白 + 碳水${estimate?.recommended_calorie_goal ? `，参考日目标 ${estimate.recommended_calorie_goal} kcal` : ''}。`,
      sourceLabel: '基于本周目标差',
      tone: 'sky',
    };
  }

  return {
    title: '训练与饮食保持同频即可',
    description:
      goalSource === 'tdee_estimate'
        ? '当前热量目标已经基于代谢画像估算，训练日无需额外复杂补偿，稳定执行更重要。'
        : '当前周波动还在可控范围内，训练日以常规计划和恢复感受为主。',
    focus: '保留 15-25 分钟活动或力量训练，配合规律进餐，比临时大起大落更容易长期坚持。',
    sourceLabel: goalSource === 'tdee_estimate' ? '基于代谢画像目标' : '基于周内执行趋势',
    tone: goalSource === 'tdee_estimate' ? 'emerald' : 'sky',
  };
}

function toneClasses(tone: SuggestionTone): string {
  if (tone === 'emerald') {
    return 'border-emerald-200 bg-emerald-50/70 text-emerald-800 dark:border-emerald-900/40 dark:bg-emerald-900/20 dark:text-emerald-200';
  }
  if (tone === 'amber') {
    return 'border-amber-200 bg-amber-50/70 text-amber-800 dark:border-amber-900/40 dark:bg-amber-900/20 dark:text-amber-200';
  }
  return 'border-sky-200 bg-sky-50/70 text-sky-800 dark:border-sky-900/40 dark:bg-sky-900/20 dark:text-sky-200';
}

export function TrainingCompensationCard({
  summary,
  budgetSnapshot,
  preference,
}: {
  summary: WeeklySummary | null;
  budgetSnapshot: DietBudgetSnapshot | null;
  preference: UserFoodPreference | null;
}) {
  const suggestion =
    extractBackendSuggestion(summary) || buildFallbackSuggestion(summary, budgetSnapshot, preference);

  return (
    <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-5 shadow-sm transition-all duration-200 hover:shadow-md">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full border border-gray-200 bg-gray-50 px-3 py-1 text-xs font-medium text-gray-700 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200">
            <Dumbbell className="h-3.5 w-3.5" />
            训练 / 补偿建议
          </div>
          <h3 className="mt-3 text-lg font-semibold text-gray-900 dark:text-gray-100">
            {suggestion.title}
          </h3>
          <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">{suggestion.description}</p>
        </div>
        <div className={`rounded-full border px-3 py-1 text-xs font-medium ${toneClasses(suggestion.tone)}`}>
          {suggestion.sourceLabel}
        </div>
      </div>

      <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="rounded-2xl border border-gray-100 dark:border-gray-800 bg-gray-50/70 dark:bg-gray-950/30 px-4 py-3">
          <div className="inline-flex items-center gap-2 text-xs font-medium text-gray-600 dark:text-gray-300">
            <Footprints className="h-3.5 w-3.5" />
            建议动作
          </div>
          <div className="mt-2 text-sm text-gray-900 dark:text-gray-100">{suggestion.focus}</div>
        </div>

        <div className="rounded-2xl border border-gray-100 dark:border-gray-800 bg-gray-50/70 dark:bg-gray-950/30 px-4 py-3">
          <div className="inline-flex items-center gap-2 text-xs font-medium text-gray-600 dark:text-gray-300">
            <HeartHandshake className="h-3.5 w-3.5" />
            执行原则
          </div>
          <div className="mt-2 text-sm text-gray-900 dark:text-gray-100">
            这张卡只做轻量建议展示，不会自动改训练或饮食数据；主路径里优先帮助你理解该“稳住”还是“轻补偿”。
          </div>
        </div>
      </div>
    </div>
  );
}
