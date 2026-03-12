import { useEffect, useMemo, useState } from 'react';
import { CheckCircle2, Loader2, Sparkles, TriangleAlert } from 'lucide-react';

import type {
  ApplySmartActionResponse,
  MealPlanPreviewAction,
} from '../../types';
import { useAuth } from '../../contexts';
import { applySmartAction } from '../../services/api/agent';
import type { TraceStep } from './AgentThinkingBlock';
import { FlashcardCarousel, type FlashcardItem } from './FlashcardCarousel';

interface WeekPlanPreviewCardProps {
  action: MealPlanPreviewAction;
  trace: TraceStep[];
  sessionId?: string;
}

interface MealCandidate {
  dish_name: string;
  calories?: number;
  protein?: number;
  fat?: number;
  carbs?: number;
  nutrition_source?: string;
  nutrition_confidence?: number;
  description?: string;
}

function buildMealKey(planDate: string, mealType: string): string {
  return `${planDate}-${mealType}`;
}

function parseExistingResults(
  trace: TraceStep[],
  actionId: string
): Record<string, ApplySmartActionResponse> {
  const resultMap: Record<string, ApplySmartActionResponse> = {};
  for (const step of [...trace].reverse()) {
    if (step.action !== 'smart_action_result') continue;
    if (!step.content || typeof step.content !== 'object') continue;
    const payload = step.content as Record<string, unknown>;
    if (payload.action_id !== actionId) continue;
    const actionKind = String(payload.action_kind || '');
    if (!actionKind || resultMap[actionKind]) continue;
    resultMap[actionKind] = {
      action_id: String(payload.action_id || actionId),
      action_kind: actionKind,
      mode: String(payload.mode || 'user_select'),
      applied: Boolean(payload.applied),
      used_provider: String(payload.used_provider || 'unknown'),
      message: String(payload.message || '操作已执行'),
      result:
        payload.result && typeof payload.result === 'object'
          ? (payload.result as Record<string, unknown>)
          : null,
    };
  }
  return resultMap;
}

export function WeekPlanPreviewCard({
  action,
  trace,
  sessionId,
}: WeekPlanPreviewCardProps) {
  const { token } = useAuth();
  const resolvedSessionId = sessionId || action.session_id;
  const previewDays = Array.isArray(action.preview_days) ? action.preview_days : [];
  const plannedMeals = Array.isArray(action.planned_meals) ? action.planned_meals : [];
  const trainingPlan = Array.isArray(action.training_plan) ? action.training_plan : [];
  const relaxSuggestions = Array.isArray(action.relax_suggestions) ? action.relax_suggestions : [];
  const [loadingKind, setLoadingKind] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [savedPreferenceOnly, setSavedPreferenceOnly] = useState(false);
  const [editablePlannedMeals, setEditablePlannedMeals] = useState(plannedMeals);
  const [candidateIndexByMeal, setCandidateIndexByMeal] = useState<Record<string, number>>({});
  const [lastRequest, setLastRequest] = useState<{
    actionKind: 'apply_week_plan' | 'fetch_weekly_progress';
    payload: Record<string, unknown>;
  } | null>(null);

  const traceResults = useMemo(
    () => parseExistingResults(trace, action.action_id),
    [trace, action.action_id]
  );
  const [results, setResults] = useState<Record<string, ApplySmartActionResponse>>(traceResults);

  useEffect(() => {
    if (Object.keys(traceResults).length > 0) {
      setResults((prev) => ({ ...prev, ...traceResults }));
    }
  }, [traceResults]);

  useEffect(() => {
    setEditablePlannedMeals(plannedMeals);
    const defaults: Record<string, number> = {};
    previewDays.forEach((day) => {
      const dayMeals = Array.isArray(day.meals) ? day.meals : [];
      dayMeals.forEach((meal) => {
        defaults[buildMealKey(day.date, meal.meal_type)] = 0;
      });
    });
    setCandidateIndexByMeal(defaults);
  }, [action.action_id, plannedMeals, previewDays]);

  function upsertPlannedMeal(
    planDate: string,
    mealType: string,
    candidate: MealCandidate
  ) {
    setEditablePlannedMeals((prev) => {
      let matched = false;
      const next = prev.map((item) => {
        if (item.plan_date !== planDate || item.meal_type !== mealType) {
          return item;
        }
        matched = true;
        const originalDish =
          Array.isArray(item.dishes) && item.dishes[0] && typeof item.dishes[0] === 'object'
            ? (item.dishes[0] as Record<string, unknown>)
            : {};
        const dishPatch: Record<string, unknown> = {
          name: candidate.dish_name,
          calories: candidate.calories,
        };
        if (candidate.protein !== undefined) dishPatch.protein = candidate.protein;
        if (candidate.fat !== undefined) dishPatch.fat = candidate.fat;
        if (candidate.carbs !== undefined) dishPatch.carbs = candidate.carbs;
        if (candidate.nutrition_source !== undefined) dishPatch.nutrition_source = candidate.nutrition_source;
        if (candidate.nutrition_confidence !== undefined) dishPatch.nutrition_confidence = candidate.nutrition_confidence;
        return {
          ...item,
          dishes: [
            {
              ...originalDish,
              ...dishPatch,
            },
          ],
          notes: candidate.description || item.notes,
        };
      });
      if (!matched) {
        const dish: Record<string, unknown> = {
          name: candidate.dish_name,
          calories: candidate.calories,
        };
        if (candidate.protein !== undefined) dish.protein = candidate.protein;
        if (candidate.fat !== undefined) dish.fat = candidate.fat;
        if (candidate.carbs !== undefined) dish.carbs = candidate.carbs;
        if (candidate.nutrition_source !== undefined) dish.nutrition_source = candidate.nutrition_source;
        if (candidate.nutrition_confidence !== undefined) dish.nutrition_confidence = candidate.nutrition_confidence;
        next.push({
          plan_date: planDate,
          meal_type: mealType,
          dishes: [
            dish,
          ],
          notes: candidate.description || '由 PlanMode 个性化推荐卡写入',
        });
      }
      return next;
    });
  }

  function handleSwitchCandidate(
    planDate: string,
    mealType: string,
    candidates: MealCandidate[]
  ) {
    if (candidates.length <= 1) return;
    const mealKey = buildMealKey(planDate, mealType);
    const currentIndex = candidateIndexByMeal[mealKey] ?? 0;
    const nextIndex = (currentIndex + 1) % candidates.length;
    setCandidateIndexByMeal((prev) => ({ ...prev, [mealKey]: nextIndex }));
    upsertPlannedMeal(planDate, mealType, candidates[nextIndex]);
  }

  async function submitAction(
    actionKind: 'apply_week_plan' | 'fetch_weekly_progress',
    payload: Record<string, unknown>,
    isRetry: boolean = false
  ) {
    if (!token) {
      setError('请先登录后再操作。');
      return;
    }
    if (!resolvedSessionId) {
      setError('会话 ID 缺失，请刷新后重试。');
      return;
    }
    if (!isRetry) {
      setLastRequest({ actionKind, payload });
    }
    setLoadingKind(actionKind);
    setError(null);
    try {
      const response = await applySmartAction(
        {
          session_id: resolvedSessionId,
          action_id: action.action_id,
          action_kind: actionKind,
          mode: 'user_select',
          payload,
        },
        token || undefined
      );
      setResults((prev) => ({ ...prev, [actionKind]: response }));
    } catch (err) {
      setError(err instanceof Error ? err.message : '执行失败');
    } finally {
      setLoadingKind(null);
    }
  }

  const applyWeekResult = results.apply_week_plan;
  const weeklyProgressResult = results.fetch_weekly_progress;
  const hasPlannedMeals = editablePlannedMeals.length > 0;
  const canApplyWeekPlan = !applyWeekResult && loadingKind === null && hasPlannedMeals;
  const isTimeoutError = Boolean(error && error.includes('重试获取结果'));

  const flashcards: FlashcardItem[] = [
    {
      id: 'strategy',
      title: '本周策略',
      content: (
        <>
          <div className="text-xs text-gray-600 dark:text-gray-300">
            强度：{action.weekly_intensity_label} · {action.weekly_hint}
          </div>
          {action.llm_supplement && (
            <div className="mt-2 inline-flex items-start gap-1.5 rounded-md bg-emerald-100/80 dark:bg-emerald-900/40 px-2 py-1 text-xs text-emerald-700 dark:text-emerald-200">
              <Sparkles className="h-3.5 w-3.5 mt-0.5 shrink-0" />
              <span>{action.llm_supplement}</span>
            </div>
          )}
        </>
      ),
    },
    {
      id: 'meals',
      title: '个性化周餐次预览',
      content: (
        <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
          {previewDays.length === 0 && (
            <div className="rounded-md border border-dashed border-gray-300 dark:border-gray-700 px-2 py-2 text-xs text-gray-500 dark:text-gray-400">
              暂无可展示的餐次，请返回上一步调整偏好后重试。
            </div>
          )}
          {previewDays.map((day) => {
            const dayMeals = Array.isArray(day.meals) ? day.meals : [];
            return (
              <div
                key={`${day.date}-${day.weekday}`}
                className="rounded-md border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-2 py-1.5"
              >
                <div className="text-xs font-medium text-gray-700 dark:text-gray-200">
                  {day.date} · {day.weekday}
                </div>
                <ul className="mt-1 space-y-1 text-xs text-gray-600 dark:text-gray-300">
                  {dayMeals.map((meal) => (
                    (() => {
                      const mealKey = buildMealKey(day.date, meal.meal_type);
                      const candidates = Array.isArray(meal.candidates)
                        ? (meal.candidates as MealCandidate[])
                        : [];
                      const candidateIndex = candidateIndexByMeal[mealKey] ?? 0;
                      const selectedCandidate = candidates[candidateIndex];
                      const selectedDishName = selectedCandidate?.dish_name || meal.dish_name;
                      const selectedCalories = selectedCandidate?.calories ?? meal.calories;
                      const selectedDescription = selectedCandidate?.description || meal.description;
                      return (
                        <li key={mealKey} className="rounded border border-gray-200 dark:border-gray-700 px-2 py-1.5">
                          <div className="flex items-center justify-between gap-2">
                            <span>
                              {meal.meal_type}：{selectedDishName}
                            </span>
                            <span className="text-[11px] text-gray-500 dark:text-gray-400">
                              {selectedCalories ? `${selectedCalories} kcal` : '--'}
                            </span>
                          </div>
                          {selectedDescription && (
                            <div className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
                              {selectedDescription}
                            </div>
                          )}
                          {candidates.length > 1 && (
                            <div className="mt-1 flex items-center justify-between">
                              <span className="text-[11px] text-emerald-600 dark:text-emerald-300">
                                候选 {candidateIndex + 1}/{candidates.length}
                              </span>
                              <button
                                type="button"
                                onClick={() =>
                                  handleSwitchCandidate(day.date, meal.meal_type, candidates)
                                }
                                className="rounded border border-emerald-300 px-2 py-0.5 text-[11px] text-emerald-700 hover:bg-emerald-100 dark:border-emerald-700 dark:text-emerald-300 dark:hover:bg-emerald-900/30"
                              >
                                换一个候选
                              </button>
                            </div>
                          )}
                        </li>
                      );
                    })()
                  ))}
                </ul>
              </div>
            );
          })}
          {!hasPlannedMeals && (
            <div className="text-xs text-amber-600 dark:text-amber-300">
              当前预览未生成可写入数据，暂不可提交本周计划。
            </div>
          )}
        </div>
      ),
    },
    {
      id: 'training',
      title: '训练建议卡（仅建议）',
      content: trainingPlan.length === 0 ? (
        <div className="text-xs text-gray-500 dark:text-gray-400">暂未生成训练建议。</div>
      ) : (
        <ul className="space-y-1 text-xs text-gray-600 dark:text-gray-300">
          {trainingPlan.map((item) => (
            <li key={`${item.date}-${item.title}`} className="list-disc ml-4">
              {item.date} · {item.title}：{item.description}
            </li>
          ))}
        </ul>
      ),
    },
    {
      id: 'relax',
      title: '放松场景建议',
      content: relaxSuggestions.length === 0 ? (
        <div className="text-xs text-gray-500 dark:text-gray-400">暂未生成放松场景建议。</div>
      ) : (
        <ul className="space-y-1 text-xs text-gray-600 dark:text-gray-300">
          {relaxSuggestions.map((item, idx) => (
            <li key={`${idx}-${item}`} className="list-disc ml-4">
              {item}
            </li>
          ))}
        </ul>
      ),
    },
    {
      id: 'actions',
      title: '写入与周进度',
      content: (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              disabled={!canApplyWeekPlan}
              onClick={() =>
                submitAction('apply_week_plan', {
                  planned_meals: editablePlannedMeals,
                  weekly_intensity: action.weekly_intensity,
                })
              }
              className="rounded-lg bg-emerald-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-600 disabled:cursor-not-allowed disabled:opacity-60"
            >
              确认写入本周计划
            </button>
            <button
              type="button"
              disabled={loadingKind !== null}
              onClick={() => setSavedPreferenceOnly(true)}
              className="rounded-lg border border-gray-300 dark:border-gray-600 px-3 py-1.5 text-xs text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-60"
            >
              仅保存偏好
            </button>
            {applyWeekResult && (
              <span className="inline-flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-300">
                <CheckCircle2 className="h-3.5 w-3.5" />
                {applyWeekResult.message}
              </span>
            )}
            {savedPreferenceOnly && !applyWeekResult && (
              <span className="text-xs text-emerald-700 dark:text-emerald-300">
                已保留偏好设置，可稍后再写入本周计划。
              </span>
            )}
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <button
              type="button"
              disabled={loadingKind !== null}
              onClick={() =>
                submitAction('fetch_weekly_progress', {
                  intensity_level: action.weekly_intensity,
                })
              }
              className="rounded-lg border border-emerald-300 px-3 py-1.5 text-xs text-emerald-700 hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-60 dark:border-emerald-700 dark:text-emerald-300 dark:hover:bg-emerald-900/30"
            >
              查看当前周进度
            </button>
            {weeklyProgressResult && (
              <span className="text-xs text-emerald-700 dark:text-emerald-300">
                {weeklyProgressResult.message}
              </span>
            )}
          </div>
        </>
      ),
    },
  ];

  return (
    <div className="mt-3 rounded-xl border border-emerald-200 dark:border-emerald-800 bg-emerald-50/60 dark:bg-emerald-900/20 p-3">
      <div className="text-sm font-medium text-emerald-800 dark:text-emerald-200">{action.title}</div>
      {action.description && (
        <p className="mt-1 text-xs text-emerald-700 dark:text-emerald-300">{action.description}</p>
      )}

      <FlashcardCarousel items={flashcards} className="mt-3" />

      {error && (
        <div className="mt-2 rounded-lg bg-red-50 dark:bg-red-900/30 px-2.5 py-2 text-xs text-red-600 dark:text-red-300">
          <div className="inline-flex items-center gap-1.5">
            <TriangleAlert className="h-3.5 w-3.5" />
            {error}
          </div>
          {isTimeoutError && lastRequest && (
            <div className="mt-2">
              <button
                type="button"
                disabled={loadingKind !== null}
                onClick={() => submitAction(lastRequest.actionKind, lastRequest.payload, true)}
                className="rounded border border-red-300 bg-white/70 px-2 py-1 text-[11px] text-red-700 hover:bg-white disabled:cursor-not-allowed disabled:opacity-60 dark:border-red-700 dark:bg-red-900/20 dark:text-red-200"
              >
                重试获取结果
              </button>
            </div>
          )}
        </div>
      )}

      {loadingKind && (
        <div className="mt-2 inline-flex items-center gap-1 text-xs text-emerald-700 dark:text-emerald-300">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          正在处理操作...
        </div>
      )}
    </div>
  );
}
