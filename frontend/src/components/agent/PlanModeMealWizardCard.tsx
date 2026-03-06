import { useEffect, useMemo, useState } from 'react';
import { Loader2, Timer, TriangleAlert } from 'lucide-react';

import type {
  ApplySmartActionResponse,
  MealPlanPlanModeAction,
  MealPlanPreviewAction,
} from '../../types';
import { useAuth } from '../../contexts';
import { applySmartAction } from '../../services/api/agent';
import type { TraceStep } from './AgentThinkingBlock';
import { WeekPlanPreviewCard } from './WeekPlanPreviewCard';

interface PlanModeMealWizardCardProps {
  action: MealPlanPlanModeAction;
  trace: TraceStep[];
  sessionId?: string;
}

function parseSubmitResult(
  trace: TraceStep[],
  actionId: string
): ApplySmartActionResponse | null {
  for (const step of [...trace].reverse()) {
    if (step.action !== 'smart_action_result') continue;
    if (!step.content || typeof step.content !== 'object') continue;
    const payload = step.content as Record<string, unknown>;
    if (payload.action_id !== actionId) continue;
    if (payload.action_kind !== 'submit_plan_profile') continue;
    return {
      action_id: String(payload.action_id || actionId),
      action_kind: String(payload.action_kind || 'submit_plan_profile'),
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
  return null;
}

function extractPreviewAction(
  response: ApplySmartActionResponse | null
): MealPlanPreviewAction | null {
  if (!response || !response.result || typeof response.result !== 'object') return null;
  const previewAction = (response.result as Record<string, unknown>).preview_action;
  if (!previewAction || typeof previewAction !== 'object') return null;
  if ((previewAction as Record<string, unknown>).action_type !== 'meal_plan_preview_card') return null;
  return previewAction as unknown as MealPlanPreviewAction;
}

function toggleArrayValue(values: string[], value: string): string[] {
  if (!value) return values;
  if (values.includes(value)) {
    return values.filter((item) => item !== value);
  }
  return [...values, value];
}

export function PlanModeMealWizardCard({
  action,
  trace,
  sessionId,
}: PlanModeMealWizardCardProps) {
  const { token } = useAuth();
  const resolvedSessionId = sessionId || action.session_id;
  const wizardSteps =
    Array.isArray(action.steps) && action.steps.length > 0
      ? action.steps
      : [
          { id: 'goal_food', title: '饮食目标与食物类型' },
          { id: 'restriction', title: '限制与过敏' },
          { id: 'relax', title: '放松场景方式' },
          { id: 'weekly_intensity', title: '周进度强度与训练偏好' },
        ];
  const goalOptions = Array.isArray(action.goal_options) ? action.goal_options : [];
  const foodTypeOptions = Array.isArray(action.food_type_options) ? action.food_type_options : [];
  const restrictionOptions = Array.isArray(action.restriction_options) ? action.restriction_options : [];
  const relaxModeOptions = Array.isArray(action.relax_mode_options) ? action.relax_mode_options : [];
  const weeklyIntensityOptions = Array.isArray(action.weekly_intensity_options)
    ? action.weekly_intensity_options
    : [];
  const trainingFocusOptions = Array.isArray(action.training_focus_options)
    ? action.training_focus_options
    : [];
  const [stepIndex, setStepIndex] = useState(0);
  const [secondsLeft, setSecondsLeft] = useState(action.timeout_seconds || 10);
  const [timedOut, setTimedOut] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [goal, setGoal] = useState(action.defaults?.goal || goalOptions[0]?.value || 'fat_loss');
  const [foodTypes, setFoodTypes] = useState<string[]>([]);
  const [foodTypeCustom, setFoodTypeCustom] = useState('');
  const [restrictions, setRestrictions] = useState<string[]>([]);
  const [allergies, setAllergies] = useState<string>('');
  const [restrictionCustom, setRestrictionCustom] = useState('');
  const [relaxModes, setRelaxModes] = useState<string[]>([]);
  const [relaxCustom, setRelaxCustom] = useState('');
  const [weeklyIntensity, setWeeklyIntensity] = useState(
    action.defaults?.weekly_intensity || weeklyIntensityOptions[0]?.value || 'balanced'
  );
  const [trainingFocus, setTrainingFocus] = useState(
    action.defaults?.training_focus || trainingFocusOptions[0]?.value || 'low_impact'
  );
  const [trainingMinutesPerDay, setTrainingMinutesPerDay] = useState(
    action.defaults?.training_minutes_per_day || 25
  );
  const [trainingDaysPerWeek, setTrainingDaysPerWeek] = useState(
    action.defaults?.training_days_per_week || 3
  );
  const [cookTimeMinutes, setCookTimeMinutes] = useState(action.defaults?.cook_time_minutes || 30);
  const [specialDays, setSpecialDays] = useState('');
  const [trainingCustom, setTrainingCustom] = useState('');

  const submitResultFromTrace = useMemo(
    () => parseSubmitResult(trace, action.action_id),
    [trace, action.action_id]
  );
  const [submitResult, setSubmitResult] = useState<ApplySmartActionResponse | null>(submitResultFromTrace);
  const [previewAction, setPreviewAction] = useState<MealPlanPreviewAction | null>(
    extractPreviewAction(submitResultFromTrace)
  );

  useEffect(() => {
    if (submitResultFromTrace) {
      setSubmitResult(submitResultFromTrace);
      setPreviewAction(extractPreviewAction(submitResultFromTrace));
    }
  }, [submitResultFromTrace]);

  const canCountDown = !timedOut && !previewAction && !isSubmitting;
  useEffect(() => {
    if (!canCountDown) return;
    if (secondsLeft <= 0) {
      setTimedOut(true);
      return;
    }
    const timer = window.setTimeout(() => {
      setSecondsLeft((prev) => Math.max(prev - 1, 0));
    }, 1000);
    return () => window.clearTimeout(timer);
  }, [canCountDown, secondsLeft]);

  async function handleSubmitProfile() {
    if (!token) {
      setError('请先登录后再提交。');
      return;
    }
    if (!resolvedSessionId) {
      setError('会话 ID 缺失，请刷新后重试。');
      return;
    }
    setIsSubmitting(true);
    setError(null);
    try {
      const response = await applySmartAction(
        {
          session_id: resolvedSessionId,
          action_id: action.action_id,
          action_kind: 'submit_plan_profile',
          mode: 'user_select',
          payload: {
            goal,
            food_types: foodTypes,
            food_type_custom: foodTypeCustom,
            restrictions,
            allergies: allergies
              .split(/[,，、\n]/)
              .map((item) => item.trim())
              .filter(Boolean),
            restriction_custom: restrictionCustom,
            relax_modes: relaxModes,
            relax_custom: relaxCustom,
            weekly_intensity: weeklyIntensity,
            training_focus: trainingFocus,
            training_minutes_per_day: trainingMinutesPerDay,
            training_days_per_week: trainingDaysPerWeek,
            cook_time_minutes: cookTimeMinutes,
            special_days: specialDays,
            training_custom: trainingCustom,
          },
        },
        token || undefined
      );
      setSubmitResult(response);
      setPreviewAction(extractPreviewAction(response));
    } catch (err) {
      setError(err instanceof Error ? err.message : '提交失败');
    } finally {
      setIsSubmitting(false);
    }
  }

  const totalSteps = wizardSteps.length || 4;
  const isLastStep = stepIndex >= totalSteps - 1;

  return (
    <div className="mt-3 rounded-xl border border-indigo-200 dark:border-indigo-800 bg-indigo-50/70 dark:bg-indigo-900/20 p-3">
      <div className="text-sm font-medium text-indigo-800 dark:text-indigo-200">{action.title}</div>
      {action.description && (
        <p className="mt-1 text-xs text-indigo-700 dark:text-indigo-300">{action.description}</p>
      )}

      {!previewAction && (
        <div className="mt-3 rounded-lg border border-indigo-100 dark:border-indigo-800/60 bg-white/80 dark:bg-gray-900/50 p-2.5">
          <div className="text-xs font-medium text-gray-700 dark:text-gray-200">
            Step {stepIndex + 1}/{totalSteps} · {wizardSteps[stepIndex]?.title || '个性化配置'}
          </div>
          {wizardSteps[stepIndex]?.hint && (
            <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              {wizardSteps[stepIndex].hint}
            </div>
          )}

          {stepIndex === 0 && (
            <div className="mt-3 space-y-3">
              <div>
                <div className="text-xs font-medium text-gray-700 dark:text-gray-200">饮食目标</div>
                <div className="mt-1 flex flex-wrap gap-2">
                  {goalOptions.map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => setGoal(option.value)}
                      className={`rounded-full border px-2.5 py-1 text-xs ${
                        goal === option.value
                          ? 'border-indigo-500 bg-indigo-500 text-white'
                          : 'border-indigo-300 text-indigo-700 dark:border-indigo-700 dark:text-indigo-300'
                      }`}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <div className="text-xs font-medium text-gray-700 dark:text-gray-200">偏好食物类型</div>
                <div className="mt-1 flex flex-wrap gap-2">
                  {foodTypeOptions.map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => setFoodTypes((prev) => toggleArrayValue(prev, option.value))}
                      className={`rounded-full border px-2.5 py-1 text-xs ${
                        foodTypes.includes(option.value)
                          ? 'border-indigo-500 bg-indigo-100 text-indigo-800 dark:bg-indigo-900/40 dark:text-indigo-200'
                          : 'border-gray-300 text-gray-600 dark:border-gray-700 dark:text-gray-300'
                      }`}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
                <input
                  value={foodTypeCustom}
                  onChange={(event) => setFoodTypeCustom(event.target.value)}
                  placeholder="其他食物偏好（可选）"
                  className="mt-2 w-full rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-xs text-gray-700 dark:text-gray-200"
                />
              </div>
            </div>
          )}

          {stepIndex === 1 && (
            <div className="mt-3 space-y-3">
              <div>
                <div className="text-xs font-medium text-gray-700 dark:text-gray-200">饮食限制</div>
                <div className="mt-1 flex flex-wrap gap-2">
                  {restrictionOptions.map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => setRestrictions((prev) => toggleArrayValue(prev, option.value))}
                      className={`rounded-full border px-2.5 py-1 text-xs ${
                        restrictions.includes(option.value)
                          ? 'border-indigo-500 bg-indigo-100 text-indigo-800 dark:bg-indigo-900/40 dark:text-indigo-200'
                          : 'border-gray-300 text-gray-600 dark:border-gray-700 dark:text-gray-300'
                      }`}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </div>
              <input
                value={restrictionCustom}
                onChange={(event) => setRestrictionCustom(event.target.value)}
                placeholder="其他限制（可选）"
                className="w-full rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-xs text-gray-700 dark:text-gray-200"
              />
              <input
                value={allergies}
                onChange={(event) => setAllergies(event.target.value)}
                placeholder="过敏原（可选，逗号分隔）"
                className="w-full rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-xs text-gray-700 dark:text-gray-200"
              />
            </div>
          )}

          {stepIndex === 2 && (
            <div className="mt-3 space-y-3">
              <div>
                <div className="text-xs font-medium text-gray-700 dark:text-gray-200">放松场景方式</div>
                <div className="mt-1 flex flex-wrap gap-2">
                  {relaxModeOptions.map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => setRelaxModes((prev) => toggleArrayValue(prev, option.value))}
                      className={`rounded-full border px-2.5 py-1 text-xs ${
                        relaxModes.includes(option.value)
                          ? 'border-indigo-500 bg-indigo-100 text-indigo-800 dark:bg-indigo-900/40 dark:text-indigo-200'
                          : 'border-gray-300 text-gray-600 dark:border-gray-700 dark:text-gray-300'
                      }`}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </div>
              <input
                value={relaxCustom}
                onChange={(event) => setRelaxCustom(event.target.value)}
                placeholder="其他放松方式（可选）"
                className="w-full rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-xs text-gray-700 dark:text-gray-200"
              />
            </div>
          )}

          {stepIndex === 3 && (
            <div className="mt-3 space-y-3">
              <div>
                <div className="text-xs font-medium text-gray-700 dark:text-gray-200">周进度强度</div>
                <div className="mt-1 flex flex-wrap gap-2">
                  {weeklyIntensityOptions.map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => setWeeklyIntensity(option.value)}
                      className={`rounded-full border px-2.5 py-1 text-xs ${
                        weeklyIntensity === option.value
                          ? 'border-indigo-500 bg-indigo-500 text-white'
                          : 'border-indigo-300 text-indigo-700 dark:border-indigo-700 dark:text-indigo-300'
                      }`}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <div className="text-xs font-medium text-gray-700 dark:text-gray-200">训练偏好</div>
                <div className="mt-1 flex flex-wrap gap-2">
                  {trainingFocusOptions.map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => setTrainingFocus(option.value)}
                      className={`rounded-full border px-2.5 py-1 text-xs ${
                        trainingFocus === option.value
                          ? 'border-indigo-500 bg-indigo-500 text-white'
                          : 'border-indigo-300 text-indigo-700 dark:border-indigo-700 dark:text-indigo-300'
                      }`}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                <input
                  type="number"
                  min={10}
                  max={120}
                  value={trainingMinutesPerDay}
                  onChange={(event) => setTrainingMinutesPerDay(Number(event.target.value))}
                  placeholder="单日训练分钟"
                  className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-xs text-gray-700 dark:text-gray-200"
                />
                <input
                  type="number"
                  min={1}
                  max={7}
                  value={trainingDaysPerWeek}
                  onChange={(event) => setTrainingDaysPerWeek(Number(event.target.value))}
                  placeholder="每周训练天数"
                  className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-xs text-gray-700 dark:text-gray-200"
                />
                <input
                  type="number"
                  min={10}
                  max={180}
                  value={cookTimeMinutes}
                  onChange={(event) => setCookTimeMinutes(Number(event.target.value))}
                  placeholder="每日烹饪分钟"
                  className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-xs text-gray-700 dark:text-gray-200"
                />
              </div>
              <input
                value={specialDays}
                onChange={(event) => setSpecialDays(event.target.value)}
                placeholder="特殊日程（聚餐/旅行等，可选）"
                className="w-full rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-xs text-gray-700 dark:text-gray-200"
              />
              <input
                value={trainingCustom}
                onChange={(event) => setTrainingCustom(event.target.value)}
                placeholder="训练备注（可选）"
                className="w-full rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-xs text-gray-700 dark:text-gray-200"
              />
            </div>
          )}

          <div className="mt-3 flex items-center justify-between gap-2">
            <button
              type="button"
              disabled={isSubmitting || stepIndex === 0}
              onClick={() => setStepIndex((prev) => Math.max(prev - 1, 0))}
              className="rounded-lg border border-gray-300 dark:border-gray-600 px-3 py-1.5 text-xs text-gray-700 dark:text-gray-200 disabled:cursor-not-allowed disabled:opacity-60"
            >
              上一步
            </button>
            {!isLastStep ? (
              <button
                type="button"
                disabled={isSubmitting}
                onClick={() => setStepIndex((prev) => Math.min(prev + 1, totalSteps - 1))}
                className="rounded-lg bg-indigo-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-600 disabled:cursor-not-allowed disabled:opacity-60"
              >
                下一步
              </button>
            ) : (
              <button
                type="button"
                disabled={isSubmitting}
                onClick={handleSubmitProfile}
                className="rounded-lg bg-indigo-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-600 disabled:cursor-not-allowed disabled:opacity-60"
              >
                生成个性化周计划预览
              </button>
            )}
          </div>
        </div>
      )}

      {previewAction && (
        <WeekPlanPreviewCard
          action={previewAction}
          trace={trace}
          sessionId={resolvedSessionId || previewAction.session_id}
        />
      )}

      {!previewAction && canCountDown && (
        <div className="mt-3 inline-flex items-center gap-1 text-xs text-indigo-700 dark:text-indigo-300">
          <Timer className="h-3.5 w-3.5" />
          {secondsLeft}s 后自动转为“仅建议模式”（不写入数据）
        </div>
      )}

      {timedOut && !previewAction && (
        <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-2 text-xs text-amber-700 dark:border-amber-800 dark:bg-amber-900/30 dark:text-amber-300">
          {action.default_timeout_suggestion || '已超时：仅保留建议，不会自动执行写入动作。'}
        </div>
      )}

      {submitResult && !previewAction && (
        <div className="mt-2 text-xs text-indigo-700 dark:text-indigo-300">
          {submitResult.message}
        </div>
      )}

      {error && (
        <div className="mt-2 inline-flex items-center gap-1.5 rounded-lg bg-red-50 dark:bg-red-900/30 px-2.5 py-2 text-xs text-red-600 dark:text-red-300">
          <TriangleAlert className="h-3.5 w-3.5" />
          {error}
        </div>
      )}

      {isSubmitting && (
        <div className="mt-2 inline-flex items-center gap-1 text-xs text-indigo-700 dark:text-indigo-300">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          正在生成个性化方案...
        </div>
      )}
    </div>
  );
}
