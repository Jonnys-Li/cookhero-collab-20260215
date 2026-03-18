import type {
  DietBudgetSnapshot,
  MetabolicEstimate,
  MetabolicProfile,
  UserFoodPreference,
} from '../../types/diet';

const ACTIVITY_LEVEL_LABELS: Record<string, string> = {
  sedentary: '久坐为主',
  light: '轻度活动',
  moderate: '中等活动',
  active: '高活动量',
  very_active: '非常活跃',
};

const GOAL_INTENT_LABELS: Record<string, string> = {
  fat_loss: '减脂',
  maintain: '维持',
  muscle_gain: '增肌',
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function readSavedCalorieGoal(preference: UserFoodPreference | null | undefined): number | null {
  if (!preference) return null;
  if (typeof preference.calorie_goal === 'number' && Number.isFinite(preference.calorie_goal)) {
    return preference.calorie_goal;
  }

  const stats = isRecord(preference.stats) ? preference.stats : null;
  const goals = stats && isRecord(stats.goals) ? stats.goals : null;
  const fromGoals = goals?.calorie_goal;
  if (typeof fromGoals === 'number' && Number.isFinite(fromGoals)) return fromGoals;
  return null;
}

function readMetabolicProfile(
  preference: UserFoodPreference | null | undefined
): MetabolicProfile | null {
  if (!preference) return null;
  if (isRecord(preference.metabolic_profile)) {
    return preference.metabolic_profile as MetabolicProfile;
  }
  const stats = isRecord(preference.stats) ? preference.stats : null;
  const fromStats = stats?.metabolic_profile;
  if (isRecord(fromStats)) {
    return fromStats as MetabolicProfile;
  }
  return null;
}

function formatProfileSummary(profile: MetabolicProfile | null): string | null {
  if (!profile) return null;
  const parts = [
    typeof profile.age === 'number' ? `${profile.age} 岁` : null,
    profile.biological_sex === 'male' ? '男' : profile.biological_sex === 'female' ? '女' : null,
    typeof profile.height_cm === 'number' ? `${profile.height_cm} cm` : null,
    typeof profile.weight_kg === 'number' ? `${profile.weight_kg} kg` : null,
    profile.activity_level ? ACTIVITY_LEVEL_LABELS[profile.activity_level] || profile.activity_level : null,
    profile.goal_intent ? GOAL_INTENT_LABELS[profile.goal_intent] || profile.goal_intent : null,
  ].filter(Boolean);

  return parts.length ? parts.join(' · ') : null;
}

function isEstimateAligned(
  savedGoal: number | null,
  estimate: MetabolicEstimate | null
): boolean {
  if (savedGoal === null || !estimate || !estimate.is_complete) return false;
  return Math.abs(savedGoal - estimate.recommended_calorie_goal) <= 10;
}

function describeGoalSource(
  budgetSnapshot: DietBudgetSnapshot | null | undefined,
  preference: UserFoodPreference | null | undefined
): {
  sourceLabel: string;
  summary: string;
  helper: string;
  badgeTone: 'emerald' | 'sky' | 'amber' | 'slate';
} {
  const savedGoal = readSavedCalorieGoal(preference);
  const estimate = preference?.metabolic_estimate ?? null;
  const aligned = isEstimateAligned(savedGoal, estimate);
  const source = budgetSnapshot?.goal_source;

  if (source === 'explicit') {
    if (aligned) {
      return {
        sourceLabel: '代谢画像估算目标',
        summary: '当前基线目标已经和代谢画像估算值对齐。',
        helper: '系统会优先按 BMR / TDEE 推导出的建议热量作为你的固定目标。',
        badgeTone: 'emerald',
      };
    }
    return {
      sourceLabel: '用户手动目标',
      summary: '当前基线目标来自你手动保存的热量目标。',
      helper: estimate?.is_complete
        ? '代谢画像估算值仍会作为参考展示，方便你决定是否切换。'
        : '如补齐代谢画像，可额外获得 BMR / TDEE 估算参考。',
      badgeTone: 'sky',
    };
  }

  if (source === 'tdee_estimate') {
    return {
      sourceLabel: 'TDEE 估算目标',
      summary: '当前基线目标来自代谢画像估算（BMR / TDEE）。',
      helper: '后续预算会沿用这条估算链路，除非你再次手动覆盖热量目标。',
      badgeTone: 'emerald',
    };
  }

  if (source === 'avg7d') {
    return {
      sourceLabel: '近 7 天均值',
      summary: '当前基线目标来自最近 7 天平均摄入，是未设固定目标时的自动估算。',
      helper: estimate?.is_complete
        ? '如果想让目标更稳定，可以在偏好里采用代谢画像估算值。'
        : '补充代谢画像后，可生成更个体化的固定热量目标。',
      badgeTone: 'amber',
    };
  }

  if (source === 'default1800') {
    return {
      sourceLabel: '系统默认值',
      summary: '当前基线目标还没有个体化设定，系统先用默认 1800 kcal 兜底。',
      helper: estimate?.is_complete
        ? '你已经有代谢画像估算值，可以在偏好里一键采用。'
        : '补齐代谢画像或保存手动目标后，这里会切换成更明确的来源。',
      badgeTone: 'slate',
    };
  }

  if (savedGoal !== null) {
    if (aligned) {
      return {
        sourceLabel: '已采用代谢估算',
        summary: '当前保存目标和代谢画像估算一致。',
        helper: '下次预算刷新后，会直接反映为主路径里的基线目标来源。',
        badgeTone: 'emerald',
      };
    }
    return {
      sourceLabel: '已保存手动目标',
      summary: '你已经保存了热量目标，但预算来源还未返回明确标记。',
      helper: estimate?.is_complete
        ? '代谢画像估算值可作为对照，帮助你判断是否需要调整。'
        : '如需估算参考，可继续补充代谢画像。',
      badgeTone: 'sky',
    };
  }

  if (estimate?.is_complete) {
    return {
      sourceLabel: '代谢画像已可估算',
      summary: 'BMR / TDEE 已经算出，但建议目标还没有写回当前热量目标。',
      helper: '在偏好里勾选“保存时用建议目标覆盖当前热量目标”即可启用。',
      badgeTone: 'amber',
    };
  }

  return {
    sourceLabel: '目标待设置',
    summary: '当前还没有足够信息形成明确的热量目标来源。',
    helper: '你可以手动填写热量目标，或补齐代谢画像生成估算值。',
    badgeTone: 'slate',
  };
}

function toneClasses(tone: 'emerald' | 'sky' | 'amber' | 'slate'): string {
  if (tone === 'emerald') {
    return 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/40 dark:bg-emerald-900/20 dark:text-emerald-200';
  }
  if (tone === 'sky') {
    return 'border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-900/40 dark:bg-sky-900/20 dark:text-sky-200';
  }
  if (tone === 'amber') {
    return 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/40 dark:bg-amber-900/20 dark:text-amber-200';
  }
  return 'border-gray-200 bg-gray-50 text-gray-700 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200';
}

export function CalorieGoalSourceCard({
  budgetSnapshot,
  preference,
  title = '热量目标来源',
  compact = false,
}: {
  budgetSnapshot?: DietBudgetSnapshot | null;
  preference?: UserFoodPreference | null;
  title?: string;
  compact?: boolean;
}) {
  const estimate = preference?.metabolic_estimate ?? null;
  const savedGoal = readSavedCalorieGoal(preference);
  const profileSummary = formatProfileSummary(readMetabolicProfile(preference));
  const sourceInfo = describeGoalSource(budgetSnapshot, preference);
  const effectiveGoal = budgetSnapshot?.effective_goal ?? savedGoal ?? null;
  const baseGoal = budgetSnapshot?.base_goal ?? savedGoal ?? null;
  const adjustment = budgetSnapshot?.today_adjustment ?? null;

  return (
    <div
      className={`rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 shadow-sm ${
        compact ? 'p-4' : 'p-5'
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">{title}</div>
          <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            看清当前预算是怎么来的，也方便决定要不要采用代谢画像估算。
          </div>
        </div>
        <div className={`rounded-full border px-3 py-1 text-xs font-medium ${toneClasses(sourceInfo.badgeTone)}`}>
          {sourceInfo.sourceLabel}
        </div>
      </div>

      <div className={`mt-4 grid gap-3 ${compact ? 'grid-cols-1 sm:grid-cols-3' : 'grid-cols-1 md:grid-cols-3'}`}>
        <div className="rounded-2xl border border-gray-100 dark:border-gray-800 bg-gray-50/70 dark:bg-gray-950/30 px-4 py-3">
          <div className="text-[11px] text-gray-500 dark:text-gray-400">当前有效预算</div>
          <div className="mt-1 text-lg font-semibold text-gray-900 dark:text-gray-100">
            {effectiveGoal ?? '--'} kcal
          </div>
          {adjustment !== null && adjustment !== undefined ? (
            <div className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
              今日调整 {adjustment >= 0 ? '+' : ''}{adjustment} kcal
            </div>
          ) : null}
        </div>

        <div className="rounded-2xl border border-gray-100 dark:border-gray-800 bg-gray-50/70 dark:bg-gray-950/30 px-4 py-3">
          <div className="text-[11px] text-gray-500 dark:text-gray-400">基线目标</div>
          <div className="mt-1 text-lg font-semibold text-gray-900 dark:text-gray-100">
            {baseGoal ?? '--'} kcal
          </div>
          <div className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">{sourceInfo.summary}</div>
        </div>

        <div className="rounded-2xl border border-gray-100 dark:border-gray-800 bg-gray-50/70 dark:bg-gray-950/30 px-4 py-3">
          <div className="text-[11px] text-gray-500 dark:text-gray-400">代谢估算参考</div>
          <div className="mt-1 text-lg font-semibold text-gray-900 dark:text-gray-100">
            {estimate?.recommended_calorie_goal ?? '--'} kcal
          </div>
          <div className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
            {estimate?.is_complete
              ? `BMR ${estimate.bmr_kcal} / TDEE ${estimate.tdee_kcal}`
              : '补齐画像后可生成 BMR / TDEE'}
          </div>
        </div>
      </div>

      <div className="mt-4 rounded-2xl border border-gray-100 dark:border-gray-800 bg-gray-50/80 dark:bg-gray-950/30 px-4 py-3">
        <div className="text-sm font-medium text-gray-900 dark:text-gray-100">{sourceInfo.helper}</div>
        {profileSummary ? (
          <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            当前画像：{profileSummary}
          </div>
        ) : null}
        {estimate?.is_complete ? (
          <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-gray-500 dark:text-gray-400">
            <span className="rounded-full bg-white px-2.5 py-1 dark:bg-gray-900">
              公式 {estimate.formula}
            </span>
            <span className="rounded-full bg-white px-2.5 py-1 dark:bg-gray-900">
              活动系数 {estimate.activity_factor}
            </span>
            <span className="rounded-full bg-white px-2.5 py-1 dark:bg-gray-900">
              目标修正 {estimate.goal_adjustment_kcal >= 0 ? '+' : ''}{estimate.goal_adjustment_kcal} kcal
            </span>
          </div>
        ) : null}
      </div>
    </div>
  );
}
