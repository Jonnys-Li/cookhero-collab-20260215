import { useCallback, useEffect, useMemo, useState } from 'react';
import { Loader2, Save } from 'lucide-react';
import { getPreferences, updatePreferences } from '../../services/api/diet';
import type { UpdatePreferenceRequest, UserFoodPreference } from '../../types/diet';
import { trackEvent } from '../../services/api/events';

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

export function DietPreferencesForm({ token }: { token: string }) {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [dietaryRestrictions, setDietaryRestrictions] = useState('');
  const [allergies, setAllergies] = useState('');
  const [favoriteCuisines, setFavoriteCuisines] = useState('');
  const [avoidedFoods, setAvoidedFoods] = useState('');

  const [calorieGoal, setCalorieGoal] = useState<string>('');
  const [proteinGoal, setProteinGoal] = useState<string>('');
  const [fatGoal, setFatGoal] = useState<string>('');
  const [carbsGoal, setCarbsGoal] = useState<string>('');

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await getPreferences(token);
      const pref = res.preference;

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
    } catch (err) {
      const msg = err instanceof Error ? err.message : '加载饮食偏好失败';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [token]);

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
    };
  }, [
    allergies,
    avoidedFoods,
    calorieGoal,
    carbsGoal,
    dietaryRestrictions,
    favoriteCuisines,
    fatGoal,
    proteinGoal,
  ]);

  const handleSave = async () => {
    if (!token) return;
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      await updatePreferences(token, payload);
      setSuccess('已保存饮食偏好');
      trackEvent(token, 'diet_preferences_updated', {
        has_calorie_goal: payload.calorie_goal !== undefined,
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

      <div className="mt-6 text-xs text-gray-500 dark:text-gray-400">
        {/* TODO(backend): /api/v1/events is auth required.
            body: { event_name: string; props?: Record<string, unknown> }
        */}
      </div>
    </div>
  );
}

