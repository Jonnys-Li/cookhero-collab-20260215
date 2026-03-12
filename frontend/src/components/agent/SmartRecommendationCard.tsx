import { useEffect, useMemo, useRef, useState } from 'react';
import { CheckCircle2, Loader2, Timer, TriangleAlert } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';

import type {
  ApplySmartActionResponse,
  SmartMealOption,
  SmartRecommendationAction,
} from '../../types';
import { useAuth } from '../../contexts';
import { applySmartAction } from '../../services/api/agent';
import type { TraceStep } from './AgentThinkingBlock';

interface SmartRecommendationCardProps {
  action: SmartRecommendationAction;
  trace: TraceStep[];
  sessionId?: string;
  mode?: 'full' | 'next_meal' | 'review_relax';
  onStepResolved?: (status: 'applied' | 'skipped') => void;
  showSkipButton?: boolean;
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

export function SmartRecommendationCard({
  action,
  trace,
  sessionId,
  mode = 'full',
  onStepResolved,
  showSkipButton = false,
}: SmartRecommendationCardProps) {
  const { token } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const resolvedSessionId = sessionId || action.session_id;
  const dietProgressHref =
    (location.pathname.startsWith('/agent') ? '/agent/diet' : '/diet') + '#diet-week-progress';
  const defaultOption = action.next_meal_options?.[0];
  const [selectedOptionId, setSelectedOptionId] = useState(defaultOption?.option_id || '');
  const [selectedBudgetDelta, setSelectedBudgetDelta] = useState<number | null>(
    Array.isArray(action.budget_options) && action.budget_options.length > 0
      ? action.budget_options[0]
      : null
  );
  const [secondsLeft, setSecondsLeft] = useState(action.timeout_seconds || 10);
  const [timedOut, setTimedOut] = useState(false);
  const [loadingKind, setLoadingKind] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [floatingFeedback, setFloatingFeedback] = useState<string | null>(null);
  const [lastRequest, setLastRequest] = useState<{
    actionKind: 'apply_budget_adjust' | 'apply_next_meal_plan' | 'fetch_weekly_progress';
    payload: Record<string, unknown>;
  } | null>(null);

  const traceResults = useMemo(
    () => parseExistingResults(trace, action.action_id),
    [trace, action.action_id]
  );
  const [results, setResults] = useState<Record<string, ApplySmartActionResponse>>(traceResults);
  const resolvedRef = useRef(false);

  useEffect(() => {
    if (Object.keys(traceResults).length > 0) {
      setResults((prev) => ({ ...prev, ...traceResults }));
    }
  }, [traceResults]);

  useEffect(() => {
    if (mode === 'next_meal' && results.apply_next_meal_plan && !resolvedRef.current) {
      resolvedRef.current = true;
      onStepResolved?.('applied');
      setFloatingFeedback(results.apply_next_meal_plan.message || '已写入计划餐次');
    }
    if (mode === 'review_relax' && results.fetch_weekly_progress && !resolvedRef.current) {
      resolvedRef.current = true;
      onStepResolved?.('applied');
      setFloatingFeedback(results.fetch_weekly_progress.message || '已获取周进度');
    }
  }, [mode, onStepResolved, results]);

  useEffect(() => {
    if (!floatingFeedback) return;
    const timer = window.setTimeout(() => setFloatingFeedback(null), 2500);
    return () => window.clearTimeout(timer);
  }, [floatingFeedback]);

  const canCountDown =
    mode === 'full' && !timedOut && !results.apply_next_meal_plan && !results.apply_budget_adjust;
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

  const selectedOption: SmartMealOption | undefined = action.next_meal_options.find(
    (option) => option.option_id === selectedOptionId
  ) || action.next_meal_options[0];

  async function submitAction(
    actionKind: 'apply_budget_adjust' | 'apply_next_meal_plan' | 'fetch_weekly_progress',
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

  const isTimeoutError = Boolean(error && error.includes('重试获取结果'));

  return (
    <div className="relative mt-3 rounded-xl border border-violet-200 dark:border-violet-800 bg-violet-50/70 dark:bg-violet-900/20 p-3">
      <div className="text-sm font-medium text-violet-800 dark:text-violet-200">
        {action.title}
      </div>
      {action.description && (
        <p className="mt-1 text-xs text-violet-700 dark:text-violet-300">
          {action.description}
        </p>
      )}

      {mode !== 'review_relax' && (
        <div className="mt-3 rounded-lg border border-violet-100 dark:border-violet-800/60 bg-white/80 dark:bg-gray-900/50 p-2.5">
          <div className="text-xs font-medium text-gray-800 dark:text-gray-200">下一餐纠偏建议</div>
          <div className="mt-2 space-y-2">
            {action.next_meal_options.map((option) => {
              const active = option.option_id === selectedOptionId;
              return (
                <button
                  key={option.option_id}
                  type="button"
                  onClick={() => setSelectedOptionId(option.option_id)}
                  className={`w-full rounded-lg border px-2.5 py-2 text-left text-xs transition-colors ${
                    active
                      ? 'border-violet-500 bg-violet-100/80 text-violet-800 dark:border-violet-500 dark:bg-violet-900/30 dark:text-violet-200'
                      : 'border-gray-200 bg-white text-gray-600 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300'
                  }`}
                >
                  <div className="font-medium">{option.title}</div>
                  <div className="mt-0.5">{option.description}</div>
                  <div className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
                    {option.plan_date} · {option.meal_type} · {option.dish_name}
                    {option.calories ? ` · ${option.calories} kcal` : ''}
                  </div>
                </button>
              );
            })}
          </div>
          <div className="mt-2 rounded-lg border border-violet-200/70 bg-violet-50/60 px-2.5 py-2 text-xs text-violet-700 dark:border-violet-800 dark:bg-violet-900/20 dark:text-violet-200">
            变更预览：将写入 <span className="font-semibold">{selectedOption?.dish_name || '-'}</span>
            {selectedOption?.calories ? `（${selectedOption.calories} kcal）` : ''} 到下一餐计划。
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <button
              type="button"
              disabled={loadingKind !== null || !selectedOption}
              onClick={() =>
                selectedOption &&
                submitAction('apply_next_meal_plan', {
                  plan_date: selectedOption.plan_date,
                  meal_type: selectedOption.meal_type,
                  dish_name: selectedOption.dish_name,
                  calories: selectedOption.calories,
                  protein: selectedOption.protein,
                  fat: selectedOption.fat,
                  carbs: selectedOption.carbs,
                })
              }
              className="rounded-lg bg-violet-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-violet-600 disabled:cursor-not-allowed disabled:opacity-60"
            >
              一键写入计划餐次
            </button>
            {results.apply_next_meal_plan && (
              <span className="inline-flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-300">
                <CheckCircle2 className="h-3.5 w-3.5" />
                {results.apply_next_meal_plan.message}
              </span>
            )}
          </div>
        </div>
      )}

      {mode !== 'next_meal' && (
        <>
          <div className="mt-3 rounded-lg border border-violet-100 dark:border-violet-800/60 bg-white/80 dark:bg-gray-900/50 p-2.5">
            <div className="text-xs font-medium text-gray-800 dark:text-gray-200">放松场景建议</div>
            <ul className="mt-2 space-y-1 text-xs text-gray-600 dark:text-gray-300">
              {action.relax_suggestions.map((item, idx) => (
                <li key={`${idx}-${item}`} className="list-disc pl-1 ml-4">
                  {item}
                </li>
              ))}
            </ul>
          </div>

          <div className="mt-3 rounded-lg border border-violet-100 dark:border-violet-800/60 bg-white/80 dark:bg-gray-900/50 p-2.5">
            <div className="text-xs font-medium text-gray-800 dark:text-gray-200">周进度入口</div>
            <div className="mt-1 text-xs text-gray-600 dark:text-gray-300">
              {action.weekly_progress?.summary_text || '你可以一句话查看本周完成度与偏差。'}
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <button
                type="button"
                disabled={loadingKind !== null}
                onClick={() => {
                  navigate(dietProgressHref);
                  if (!resolvedRef.current) {
                    resolvedRef.current = true;
                    onStepResolved?.('applied');
                  }
                  setFloatingFeedback('已打开周进度视图');
                }}
                className="rounded-lg border border-violet-300 px-3 py-1.5 text-xs text-violet-700 hover:bg-violet-100 disabled:cursor-not-allowed disabled:opacity-60 dark:border-violet-700 dark:text-violet-300 dark:hover:bg-violet-900/30"
              >
                打开周进度视图
              </button>
            </div>
          </div>

          {Array.isArray(action.budget_options) && action.budget_options.length > 0 && (
            <div className="mt-3 rounded-lg border border-violet-100 dark:border-violet-800/60 bg-white/80 dark:bg-gray-900/50 p-2.5">
              <div className="text-xs font-medium text-gray-800 dark:text-gray-200">手动弹性预算</div>
              <div className="mt-2 flex flex-wrap gap-2">
                {action.budget_options.map((delta) => (
                  <button
                    key={delta}
                    type="button"
                    disabled={loadingKind !== null}
                    onClick={() => {
                      setSelectedBudgetDelta(delta);
                      submitAction('apply_budget_adjust', { delta_calories: delta });
                    }}
                    className="rounded-full border border-violet-300 px-2.5 py-1 text-xs text-violet-700 hover:bg-violet-100 disabled:cursor-not-allowed disabled:opacity-60 dark:border-violet-700 dark:text-violet-300 dark:hover:bg-violet-900/30"
                  >
                    +{delta} kcal
                  </button>
                ))}
              </div>
              {selectedBudgetDelta !== null && (
                <div className="mt-2 text-xs text-violet-700 dark:text-violet-300">
                  变更预览：将尝试追加 <span className="font-semibold">+{selectedBudgetDelta} kcal</span> 预算。
                </div>
              )}
              {results.apply_budget_adjust && (
                <div className="mt-2 text-xs text-emerald-600 dark:text-emerald-300">
                  {results.apply_budget_adjust.message}
                </div>
              )}
            </div>
          )}
        </>
      )}

      {canCountDown && (
        <div className="mt-3 inline-flex items-center gap-1 text-xs text-violet-700 dark:text-violet-300">
          <Timer className="h-3.5 w-3.5" />
          {secondsLeft}s 后自动转为“仅建议模式”（不写入数据）
        </div>
      )}

      {timedOut && (
        <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-2 text-xs text-amber-700 dark:border-amber-800 dark:bg-amber-900/30 dark:text-amber-300">
          {action.default_timeout_suggestion || '已超时：仅保留建议，不会自动执行写入动作。'}
        </div>
      )}

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
        <div className="mt-2 inline-flex items-center gap-1 text-xs text-violet-700 dark:text-violet-300">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          正在执行操作...
        </div>
      )}

      {showSkipButton && !resolvedRef.current && (
        <div className="mt-2">
          <button
            type="button"
            onClick={() => {
              if (resolvedRef.current) return;
              resolvedRef.current = true;
              onStepResolved?.('skipped');
            }}
            className="rounded-lg border border-gray-300 dark:border-gray-600 px-3 py-1.5 text-xs text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800"
          >
            跳过这一步
          </button>
        </div>
      )}

      {floatingFeedback && (
        <div className="absolute right-2 top-2 rounded-md bg-emerald-500/95 px-2 py-1 text-[11px] text-white shadow">
          {floatingFeedback}
        </div>
      )}
    </div>
  );
}
