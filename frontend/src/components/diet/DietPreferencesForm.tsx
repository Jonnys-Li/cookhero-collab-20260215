import { useCallback, useEffect, useMemo, useState } from 'react';
import { Loader2, Save } from 'lucide-react';
import { getPreferences, updatePreferences } from '../../services/api/diet';
import type { UpdatePreferenceRequest, UserFoodPreference } from '../../types/diet';
import { trackEvent } from '../../services/api/events';
import { CalorieGoalSourceCard } from './CalorieGoalSourceCard';

function parseTextList(value: string): string[] {
  return value
    .split(/[\n,]/g)
    .map((s) => s.trim())
    .filter(Boolean);
}

function formatTextList(values: unknown): string {
  if (!Array.isArray(values)) return '';
  return values.map(String).filter(Boolean).join(', ');
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function readStringListFromPreference(
  pref: UserFoodPreference | null,
  key: string
): string[] | null {
  if (!pref) return null;
  const direct = (pref as unknown as Record<string, unknown>)[key];
  if (Array.isArray(direct)) return direct.map(String);

  const stats = isRecord(pref.stats) ? pref.stats : null;
  const fromStats = stats ? stats[key] : null;
  if (Array.isArray(fromStats)) return fromStats.map(String);
  return null;
}

function readNumberFromPreference(
  pref: UserFoodPreference | null,
  key: string
): number | null {
  if (!pref) return null;
  const direct = (pref as unknown as Record<string, unknown>)[key];
  if (typeof direct === 'number' && Number.isFinite(direct)) return direct;

  const stats = isRecord(pref.stats) ? pref.stats : null;
  const goals = stats && isRecord(stats.goals) ? stats.goals : null;
  const fromGoals = goals ? goals[key] : null;
  if (typeof fromGoals === 'number' && Number.isFinite(fromGoals)) return fromGoals;
  return null;
}

function readMetabolicProfile(pref: UserFoodPreference | null): NonNullable<UserFoodPreference['metabolic_profile']> | null {
  if (!pref) return null;
  if (isRecord(pref.metabolic_profile)) {
    return pref.metabolic_profile as NonNullable<UserFoodPreference['metabolic_profile']>;
  }

  const stats = isRecord(pref.stats) ? pref.stats : null;
  const fromStats = stats?.metabolic_profile;
  if (isRecord(fromStats)) {
    return fromStats as NonNullable<UserFoodPreference['metabolic_profile']>;
  }
  return null;
}

const ACTIVITY_LEVEL_OPTIONS = [
  { value: 'sedentary', label: '久坐为主' },
  { value: 'light', label: '轻度活动' },
  { value: 'moderate', label: '中等活动' },
  { value: 'active', label: '高活动量' },
  { value: 'very_active', label: '非常活跃' },
] as const;

const GOAL_INTENT_OPTIONS = [
  { value: 'fat_loss', label: '减脂' },
  { value: 'maintain', label: '维持' },
  { value: 'muscle_gain', label: '增肌' },
] as const;

export function DietPreferencesForm({ token }: { token: string }) {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [preference, setPreference] = useState<UserFoodPreference | null>(null);

  const [dietaryRestrictions, setDietaryRestrictions] = useState('');
  const [allergies, setAllergies] = useState('');
  const [favoriteCuisines, setFavoriteCuisines] = useState('');
  const [avoidedFoods, setAvoidedFoods] = useState('');

  const [calorieGoal, setCalorieGoal] = useState<string>('');
  const [proteinGoal, setProteinGoal] = useState<string>('');
  const [fatGoal, setFatGoal] = useState<string>('');
  const [carbsGoal, setCarbsGoal] = useState<string>('');
  const [age, setAge] = useState('');
  const [biologicalSex, setBiologicalSex] = useState<'' | 'male' | 'female'>('');
  const [heightCm, setHeightCm] = useState('');
  const [weightKg, setWeightKg] = useState('');
  const [activityLevel, setActivityLevel] = useState<
    '' | 'sedentary' | 'light' | 'moderate' | 'active' | 'very_active'
  >('');
  const [goalIntent, setGoalIntent] = useState<'' | 'fat_loss' | 'maintain' | 'muscle_gain'>('');
  const [useEstimatedCalorieGoal, setUseEstimatedCalorieGoal] = useState(false);

  const applyPreferenceToForm = useCallback((pref: UserFoodPreference | null) => {
    setPreference(pref);
    setDietaryRestrictions(
      formatTextList(readStringListFromPreference(pref, 'dietary_restrictions'))
    );
    setAllergies(formatTextList(readStringListFromPreference(pref, 'allergies')));
    setFavoriteCuisines(
      formatTextList(readStringListFromPreference(pref, 'favorite_cuisines'))
    );
    setAvoidedFoods(formatTextList(pref?.avoided_foods));

    const calorie = readNumberFromPreference(pref, 'calorie_goal');
    const protein = readNumberFromPreference(pref, 'protein_goal');
    const fat = readNumberFromPreference(pref, 'fat_goal');
    const carbs = readNumberFromPreference(pref, 'carbs_goal');

    setCalorieGoal(typeof calorie === 'number' ? String(calorie) : '');
    setProteinGoal(typeof protein === 'number' ? String(protein) : '');
    setFatGoal(typeof fat === 'number' ? String(fat) : '');
    setCarbsGoal(typeof carbs === 'number' ? String(carbs) : '');

    const profile = readMetabolicProfile(pref);
    setAge(typeof profile?.age === 'number' ? String(profile.age) : '');
    setBiologicalSex(
      profile?.biological_sex === 'male' || profile?.biological_sex === 'female'
        ? profile.biological_sex
        : ''
    );
    setHeightCm(typeof profile?.height_cm === 'number' ? String(profile.height_cm) : '');
    setWeightKg(typeof profile?.weight_kg === 'number' ? String(profile.weight_kg) : '');
    setActivityLevel(
      profile?.activity_level &&
        ACTIVITY_LEVEL_OPTIONS.some((option) => option.value === profile.activity_level)
        ? profile.activity_level
        : ''
    );
    setGoalIntent(
      profile?.goal_intent &&
        GOAL_INTENT_OPTIONS.some((option) => option.value === profile.goal_intent)
        ? profile.goal_intent
        : ''
    );
    setUseEstimatedCalorieGoal(false);
  }, []);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await getPreferences(token);
      applyPreferenceToForm(res.preference);
    } catch (err) {
      const msg = err instanceof Error ? err.message : '加载饮食偏好失败';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [applyPreferenceToForm, token]);

  useEffect(() => {
    load();
  }, [load]);

  const payload = useMemo<UpdatePreferenceRequest>(() => {
    const safeInt = (value: string): number | undefined => {
      const trimmed = value.trim();
      if (!trimmed) return undefined;
      const parsed = Number(trimmed);
      if (!Number.isFinite(parsed)) return undefined;
      return Math.round(parsed);
    };

    const safeFloat = (value: string): number | undefined => {
      const trimmed = value.trim();
      if (!trimmed) return undefined;
      const parsed = Number(trimmed);
      if (!Number.isFinite(parsed)) return undefined;
      return parsed;
    };

    return {
      dietary_restrictions: parseTextList(dietaryRestrictions),
      allergies: parseTextList(allergies),
      favorite_cuisines: parseTextList(favoriteCuisines),
      avoided_foods: parseTextList(avoidedFoods),
      calorie_goal: safeInt(calorieGoal),
      protein_goal: safeFloat(proteinGoal),
      fat_goal: safeFloat(fatGoal),
      carbs_goal: safeFloat(carbsGoal),
      age: safeInt(age),
      biological_sex: biologicalSex || undefined,
      height_cm: safeFloat(heightCm),
      weight_kg: safeFloat(weightKg),
      activity_level: activityLevel || undefined,
      goal_intent: goalIntent || undefined,
      use_estimated_calorie_goal: useEstimatedCalorieGoal,
    };
  }, [
    allergies,
    age,
    activityLevel,
    avoidedFoods,
    biologicalSex,
    calorieGoal,
    carbsGoal,
    dietaryRestrictions,
    favoriteCuisines,
    fatGoal,
    goalIntent,
    heightCm,
    proteinGoal,
    useEstimatedCalorieGoal,
    weightKg,
  ]);

  const handleSave = async () => {
    if (!token) return;
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await updatePreferences(token, payload);
      applyPreferenceToForm(res.preference);
      setSuccess('已保存饮食偏好');
      trackEvent(token, 'diet_preferences_updated', {
        has_calorie_goal: payload.calorie_goal !== undefined,
        has_metabolic_profile:
          Boolean(payload.age)
          || Boolean(payload.biological_sex)
          || Boolean(payload.height_cm)
          || Boolean(payload.weight_kg)
          || Boolean(payload.activity_level)
          || Boolean(payload.goal_intent),
        dietary_restrictions_count: payload.dietary_restrictions?.length ?? 0,
        allergies_count: payload.allergies?.length ?? 0,
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : '保存失败，请稍后重试';
      setError(msg);
    } finally {
      setSaving(false);
    }
  };

  const metabolicEstimate = preference?.metabolic_estimate ?? null;

  return (
    <div className="flex-1 overflow-auto pr-1">
      <div className="flex items-start justify-between gap-4 mb-4">
        <div>
          <h4 className="text-base font-semibold text-gray-900 dark:text-gray-100">
            饮食偏好与目标
          </h4>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
            用逗号或换行分隔多个条目，例如：坚果, 乳制品。保存后会影响计划、推荐与分析。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={load}
            disabled={loading || saving}
            className="px-3 py-2 rounded-xl border border-gray-200 dark:border-gray-700 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-70"
          >
            刷新
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={loading || saving}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-orange-500 hover:bg-orange-600 text-white text-sm font-semibold disabled:opacity-70"
          >
            {saving ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                保存中
              </>
            ) : (
              <>
                <Save className="w-4 h-4" />
                保存
              </>
            )}
          </button>
        </div>
      </div>

      {(error || success) && (
        <div
          className={`mb-4 rounded-xl border px-4 py-3 text-sm ${
            error
              ? 'border-red-200 bg-red-50 text-red-700 dark:border-red-900/60 dark:bg-red-900/20 dark:text-red-200'
              : 'border-green-200 bg-green-50 text-green-700 dark:border-green-900/60 dark:bg-green-900/20 dark:text-green-200'
          }`}
          role={error ? 'alert' : 'status'}
        >
          {error || success}
        </div>
      )}

      <div className="mb-6">
        <CalorieGoalSourceCard
          preference={preference}
          title="当前生效目标说明"
          compact
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <label className="block">
          <span className="text-xs font-medium text-gray-600 dark:text-gray-300">
            饮食限制
          </span>
          <textarea
            value={dietaryRestrictions}
            onChange={(e) => setDietaryRestrictions(e.target.value)}
            placeholder="例如：素食, 低盐"
            className="mt-1 w-full min-h-20 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-200 dark:focus:ring-orange-900/30"
          />
        </label>

        <label className="block">
          <span className="text-xs font-medium text-gray-600 dark:text-gray-300">
            过敏原
          </span>
          <textarea
            value={allergies}
            onChange={(e) => setAllergies(e.target.value)}
            placeholder="例如：花生, 海鲜"
            className="mt-1 w-full min-h-20 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-200 dark:focus:ring-orange-900/30"
          />
        </label>

        <label className="block">
          <span className="text-xs font-medium text-gray-600 dark:text-gray-300">
            喜爱的菜系
          </span>
          <textarea
            value={favoriteCuisines}
            onChange={(e) => setFavoriteCuisines(e.target.value)}
            placeholder="例如：川菜, 日料"
            className="mt-1 w-full min-h-20 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-200 dark:focus:ring-orange-900/30"
          />
        </label>

        <label className="block">
          <span className="text-xs font-medium text-gray-600 dark:text-gray-300">
            避免的食物
          </span>
          <textarea
            value={avoidedFoods}
            onChange={(e) => setAvoidedFoods(e.target.value)}
            placeholder="例如：奶茶, 油炸"
            className="mt-1 w-full min-h-20 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-200 dark:focus:ring-orange-900/30"
          />
        </label>
      </div>

      <div className="mt-6">
        <h5 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">
          每日目标
        </h5>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <label className="block">
            <span className="text-xs font-medium text-gray-600 dark:text-gray-300">
              热量 (kcal)
            </span>
            <input
              value={calorieGoal}
              onChange={(e) => setCalorieGoal(e.target.value)}
              inputMode="numeric"
              placeholder="例如 1800"
              className="mt-1 w-full rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-200 dark:focus:ring-orange-900/30"
            />
          </label>

          <label className="block">
            <span className="text-xs font-medium text-gray-600 dark:text-gray-300">
              蛋白 (g)
            </span>
            <input
              value={proteinGoal}
              onChange={(e) => setProteinGoal(e.target.value)}
              inputMode="decimal"
              placeholder="例如 120"
              className="mt-1 w-full rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-200 dark:focus:ring-orange-900/30"
            />
          </label>

          <label className="block">
            <span className="text-xs font-medium text-gray-600 dark:text-gray-300">
              脂肪 (g)
            </span>
            <input
              value={fatGoal}
              onChange={(e) => setFatGoal(e.target.value)}
              inputMode="decimal"
              placeholder="例如 60"
              className="mt-1 w-full rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-200 dark:focus:ring-orange-900/30"
            />
          </label>

          <label className="block">
            <span className="text-xs font-medium text-gray-600 dark:text-gray-300">
              碳水 (g)
            </span>
            <input
              value={carbsGoal}
              onChange={(e) => setCarbsGoal(e.target.value)}
              inputMode="decimal"
              placeholder="例如 200"
              className="mt-1 w-full rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-200 dark:focus:ring-orange-900/30"
            />
          </label>
        </div>
      </div>

      <div className="mt-6">
        <div className="flex items-center justify-between gap-3 mb-3">
          <div>
            <h5 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              代谢画像
            </h5>
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              用结构化信息估算 BMR / TDEE，并可在保存时把建议热量写回当前目标。
            </p>
          </div>
          {metabolicEstimate && (
            <div className="rounded-2xl border border-orange-200 bg-orange-50 px-4 py-3 text-right dark:border-orange-900/60 dark:bg-orange-900/20">
              <div className="text-[11px] uppercase tracking-wide text-orange-500 dark:text-orange-300">
                估算代谢目标
              </div>
              <div className="mt-1 text-lg font-semibold text-orange-700 dark:text-orange-200">
                {metabolicEstimate.recommended_calorie_goal} kcal
              </div>
              <div className="mt-1 text-xs text-orange-700/80 dark:text-orange-200/80">
                BMR {metabolicEstimate.bmr_kcal} / TDEE {metabolicEstimate.tdee_kcal}
              </div>
            </div>
          )}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          <label className="block">
            <span className="text-xs font-medium text-gray-600 dark:text-gray-300">
              年龄
            </span>
            <input
              value={age}
              onChange={(e) => setAge(e.target.value)}
              inputMode="numeric"
              placeholder="例如 28"
              className="mt-1 w-full rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-200 dark:focus:ring-orange-900/30"
            />
          </label>

          <label className="block">
            <span className="text-xs font-medium text-gray-600 dark:text-gray-300">
              生理性别
            </span>
            <select
              value={biologicalSex}
              onChange={(e) => setBiologicalSex(e.target.value as '' | 'male' | 'female')}
              className="mt-1 w-full rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-200 dark:focus:ring-orange-900/30"
            >
              <option value="">请选择</option>
              <option value="male">男</option>
              <option value="female">女</option>
            </select>
          </label>

          <label className="block">
            <span className="text-xs font-medium text-gray-600 dark:text-gray-300">
              身高 (cm)
            </span>
            <input
              value={heightCm}
              onChange={(e) => setHeightCm(e.target.value)}
              inputMode="decimal"
              placeholder="例如 170"
              className="mt-1 w-full rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-200 dark:focus:ring-orange-900/30"
            />
          </label>

          <label className="block">
            <span className="text-xs font-medium text-gray-600 dark:text-gray-300">
              体重 (kg)
            </span>
            <input
              value={weightKg}
              onChange={(e) => setWeightKg(e.target.value)}
              inputMode="decimal"
              placeholder="例如 65"
              className="mt-1 w-full rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-200 dark:focus:ring-orange-900/30"
            />
          </label>

          <label className="block">
            <span className="text-xs font-medium text-gray-600 dark:text-gray-300">
              活动水平
            </span>
            <select
              value={activityLevel}
              onChange={(e) =>
                setActivityLevel(
                  e.target.value as
                    | ''
                    | 'sedentary'
                    | 'light'
                    | 'moderate'
                    | 'active'
                    | 'very_active'
                )
              }
              className="mt-1 w-full rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-200 dark:focus:ring-orange-900/30"
            >
              <option value="">请选择</option>
              {ACTIVITY_LEVEL_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label className="block">
            <span className="text-xs font-medium text-gray-600 dark:text-gray-300">
              当前目标方向
            </span>
            <select
              value={goalIntent}
              onChange={(e) =>
                setGoalIntent(e.target.value as '' | 'fat_loss' | 'maintain' | 'muscle_gain')
              }
              className="mt-1 w-full rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-200 dark:focus:ring-orange-900/30"
            >
              <option value="">请选择</option>
              {GOAL_INTENT_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        <label className="mt-4 flex items-start gap-3 rounded-2xl border border-gray-200 bg-gray-50 px-4 py-3 text-sm text-gray-700 dark:border-gray-700 dark:bg-gray-900/60 dark:text-gray-200">
          <input
            type="checkbox"
            aria-label="保存时用建议目标覆盖当前热量目标"
            checked={useEstimatedCalorieGoal}
            onChange={(e) => setUseEstimatedCalorieGoal(e.target.checked)}
            className="mt-0.5 h-4 w-4 rounded border-gray-300 text-orange-500 focus:ring-orange-300"
          />
          <span>
            保存时用建议目标覆盖当前热量目标
            <span className="block mt-1 text-xs text-gray-500 dark:text-gray-400">
              仅在代谢画像填写完整时生效；不勾选时只保存画像，不会改动现有热量目标。
            </span>
          </span>
        </label>
      </div>

      <div className="mt-6 text-xs text-gray-500 dark:text-gray-400">
        {/* TODO(backend): /api/v1/events is auth required.
            body: { event_name: string; props?: Record<string, unknown> }
        */}
      </div>
    </div>
  );
}
