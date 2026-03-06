import { useEffect, useMemo, useRef, useState } from 'react';
import { CheckCircle2, Loader2, Timer, TriangleAlert } from 'lucide-react';

import type {
  ApplyEmotionBudgetAdjustResponse,
  EmotionBudgetApplyMode,
  EmotionBudgetUIAction,
} from '../../types';
import { useAuth } from '../../contexts';
import { applyEmotionBudgetAdjust } from '../../services/api/agent';
import type { TraceStep } from './AgentThinkingBlock';

const DELTA_OPTIONS = [50, 100, 150] as const;

interface EmotionBudgetAdjustCardProps {
  action: EmotionBudgetUIAction;
  trace: TraceStep[];
  sessionId?: string;
}

function parseTraceResult(
  trace: TraceStep[],
  actionId: string
): ApplyEmotionBudgetAdjustResponse | null {
  for (const step of [...trace].reverse()) {
    if (step.action !== 'emotion_budget_adjust_result') continue;
    if (!step.content || typeof step.content !== 'object') continue;
    const result = step.content as Record<string, unknown>;
    if (result.action_id !== actionId) continue;
    return {
      action_id: String(result.action_id),
      requested: Number(result.requested || 0),
      applied:
        result.applied === null || result.applied === undefined
          ? null
          : Number(result.applied),
      capped: Boolean(result.capped),
      effective_goal:
        result.effective_goal === null || result.effective_goal === undefined
          ? null
          : Number(result.effective_goal),
      used_provider: String(result.used_provider || 'unknown'),
      mode: (result.mode as EmotionBudgetApplyMode) || 'user_select',
      message: String(result.message || '自动调整完成'),
    };
  }
  return null;
}

export function EmotionBudgetAdjustCard({
  action,
  trace,
  sessionId,
}: EmotionBudgetAdjustCardProps) {
  const { token } = useAuth();
  const resolvedSessionId = sessionId || action.session_id;
  const [selectedDelta, setSelectedDelta] = useState<50 | 100 | 150>(
    action.default_delta_calories
  );
  const [secondsLeft, setSecondsLeft] = useState(action.timeout_seconds);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const traceResult = useMemo(
    () => parseTraceResult(trace, action.action_id),
    [trace, action.action_id]
  );
  const [result, setResult] = useState<ApplyEmotionBudgetAdjustResponse | null>(
    traceResult
  );
  const autoTriggeredRef = useRef(false);

  useEffect(() => {
    if (traceResult) {
      setResult(traceResult);
    }
  }, [traceResult]);

  const canAutoApply =
    action.auto_apply_on_timeout &&
    !!action.can_apply &&
    !result &&
    !dismissed &&
    !isSubmitting;

  useEffect(() => {
    if (!canAutoApply) return;
    if (secondsLeft <= 0 && !autoTriggeredRef.current) {
      autoTriggeredRef.current = true;
      void handleApply(action.default_delta_calories, 'auto_timeout');
      return;
    }
    const timer = window.setTimeout(() => {
      setSecondsLeft((prev) => Math.max(prev - 1, 0));
    }, 1000);
    return () => window.clearTimeout(timer);
  }, [canAutoApply, secondsLeft, action.default_delta_calories]);

  async function handleApply(
    delta: 50 | 100 | 150,
    mode: EmotionBudgetApplyMode
  ): Promise<void> {
    if (!token) {
      setError('请先登录后再执行自动调整。');
      return;
    }
    if (!resolvedSessionId) {
      setError('当前会话 ID 缺失，请重试。');
      return;
    }

    setError(null);
    setIsSubmitting(true);
    try {
      const response = await applyEmotionBudgetAdjust(
        {
          session_id: resolvedSessionId,
          action_id: action.action_id,
          delta_calories: delta,
          mode,
          reason:
            mode === 'auto_timeout'
              ? '超时自动执行（情绪安抚）'
              : '用户确认执行（情绪安抚）',
        },
        token || undefined
      );
      setResult(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : '预算调整失败');
    } finally {
      setIsSubmitting(false);
    }
  }

  const budgetSnapshot = action.budget_snapshot;
  const showActionArea = !result && !dismissed;

  return (
    <div className="mt-3 rounded-xl border border-orange-200 dark:border-orange-800 bg-orange-50/70 dark:bg-orange-900/20 p-3">
      <div className="text-sm font-medium text-orange-800 dark:text-orange-200">
        {action.title || '自动预算调整'}
      </div>
      {action.description && (
        <p className="mt-1 text-xs text-orange-700 dark:text-orange-300">
          {action.description}
        </p>
      )}

      {budgetSnapshot && (
        <div className="mt-2 text-xs text-gray-700 dark:text-gray-300">
          当前有效预算 <span className="font-semibold">{budgetSnapshot.effective_goal ?? '--'}</span> kcal，
          剩余可调 <span className="font-semibold">{budgetSnapshot.remaining_adjustment_cap ?? '--'}</span> kcal
        </div>
      )}

      {!action.can_apply && (
        <div className="mt-2 inline-flex items-start gap-1.5 rounded-lg bg-red-50 dark:bg-red-900/30 px-2.5 py-2 text-xs text-red-600 dark:text-red-300">
          <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>{action.unavailable_reason || '当前自动预算调整不可用，请先手动管理。'}</span>
        </div>
      )}

      {showActionArea && (
        <>
          <div className="mt-3 flex flex-wrap gap-2">
            {DELTA_OPTIONS.map((delta) => {
              const isSelected = selectedDelta === delta;
              return (
                <button
                  key={delta}
                  type="button"
                  onClick={() => setSelectedDelta(delta)}
                  disabled={isSubmitting || !action.can_apply}
                  className={`rounded-full border px-2.5 py-1 text-xs transition-colors ${
                    isSelected
                      ? 'border-orange-500 bg-orange-500 text-white'
                      : 'border-orange-300 bg-white text-orange-700 dark:border-orange-700 dark:bg-gray-900 dark:text-orange-200'
                  }`}
                >
                  +{delta} kcal
                </button>
              );
            })}
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => handleApply(selectedDelta, 'user_select')}
              disabled={isSubmitting || !action.can_apply}
              className="rounded-lg bg-orange-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-orange-600 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isSubmitting ? '执行中...' : '立即应用'}
            </button>
            <button
              type="button"
              onClick={() => setDismissed(true)}
              disabled={isSubmitting}
              className="rounded-lg border border-gray-300 dark:border-gray-600 px-3 py-1.5 text-xs text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800"
            >
              暂不调整
            </button>
            {canAutoApply && (
              <div className="inline-flex items-center gap-1 text-xs text-orange-700 dark:text-orange-300">
                <Timer className="h-3.5 w-3.5" />
                {secondsLeft}s 后自动 +{action.default_delta_calories} kcal
              </div>
            )}
          </div>
        </>
      )}

      {result && (
        <div className="mt-3 rounded-lg border border-emerald-200 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-900/25 p-2.5 text-xs text-emerald-700 dark:text-emerald-300">
          <div className="inline-flex items-center gap-1.5 font-medium">
            <CheckCircle2 className="h-3.5 w-3.5" />
            调整已同步到饮食管理
          </div>
          <div className="mt-1">
            请求 +{result.requested} kcal，实际 +{result.applied ?? 0} kcal，
            当前有效预算 {result.effective_goal ?? '--'} kcal
            {result.capped ? '（已触发上限保护）' : ''}
          </div>
          <div className="mt-1 text-[11px] text-emerald-600/90 dark:text-emerald-300/90">
            Provider: {result.used_provider} · {result.message}
          </div>
        </div>
      )}

      {dismissed && !result && (
        <div className="mt-2 text-xs text-gray-600 dark:text-gray-400">
          已跳过自动调整，你仍可在饮食管理页手动调整今日预算。
        </div>
      )}

      {error && (
        <div className="mt-2 inline-flex items-center gap-1.5 rounded-lg bg-red-50 dark:bg-red-900/30 px-2.5 py-2 text-xs text-red-600 dark:text-red-300">
          <TriangleAlert className="h-3.5 w-3.5" />
          {error}
        </div>
      )}

      {isSubmitting && (
        <div className="mt-2 inline-flex items-center gap-1 text-xs text-orange-700 dark:text-orange-300">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          正在同步预算...
        </div>
      )}
    </div>
  );
}
