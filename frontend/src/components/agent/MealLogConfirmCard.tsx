import { useEffect, useMemo, useRef, useState } from 'react';
import { CheckCircle2, Loader2, TriangleAlert } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';

import type { ApplySmartActionResponse, MealLogConfirmAction } from '../../types';
import { useAuth } from '../../contexts';
import { applySmartAction } from '../../services/api/agent';
import type { TraceStep } from './AgentThinkingBlock';

interface MealLogConfirmCardProps {
  action: MealLogConfirmAction;
  trace: TraceStep[];
  sessionId?: string;
}

function formatLocalDate(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function parseExistingResult(trace: TraceStep[], actionId: string): ApplySmartActionResponse | null {
  for (const step of [...trace].reverse()) {
    if (step.action !== 'smart_action_result') continue;
    if (!step.content || typeof step.content !== 'object') continue;
    const payload = step.content as Record<string, unknown>;
    if (payload.action_id !== actionId) continue;
    if (String(payload.action_kind || '') !== 'create_diet_log') continue;
    return {
      action_id: String(payload.action_id || actionId),
      action_kind: String(payload.action_kind || 'create_diet_log'),
      mode: String(payload.mode || 'user_select'),
      applied: Boolean(payload.applied),
      used_provider: String(payload.used_provider || 'unknown'),
      message: String(payload.message || '已记录'),
      result:
        payload.result && typeof payload.result === 'object'
          ? (payload.result as Record<string, unknown>)
          : null,
    };
  }
  return null;
}

const MEAL_LABELS: Record<string, string> = {
  breakfast: '早餐',
  lunch: '午餐',
  dinner: '晚餐',
  snack: '加餐',
};

export function MealLogConfirmCard({ action, trace, sessionId }: MealLogConfirmCardProps) {
  const { token } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const resolvedSessionId = sessionId || action.session_id;

  const traceResult = useMemo(() => parseExistingResult(trace, action.action_id), [trace, action.action_id]);
  const [result, setResult] = useState<ApplySmartActionResponse | null>(traceResult);
  const [dismissed, setDismissed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const navigatedRef = useRef(false);

  const defaultDate = action.suggested_log_date || formatLocalDate(new Date());
  const defaultMealType = action.suggested_meal_type || 'snack';
  const [logDate, setLogDate] = useState(defaultDate);
  const [mealType, setMealType] = useState(defaultMealType);
  const items = useMemo(() => (Array.isArray(action.items) ? action.items : []), [action.items]);
  const hasItems = items.length > 0;

  useEffect(() => {
    // If we got a persisted result from trace, keep local state in sync.
    if (traceResult) setResult(traceResult);
  }, [traceResult]);

  const totals = useMemo(() => {
    return items.reduce(
      (acc, item) => {
        acc.calories += Number(item.calories || 0);
        acc.protein += Number(item.protein || 0);
        acc.fat += Number(item.fat || 0);
        acc.carbs += Number(item.carbs || 0);
        return acc;
      },
      { calories: 0, protein: 0, fat: 0, carbs: 0 }
    );
  }, [action.items]);

  const dietBase = location.pathname.startsWith('/agent') ? '/agent/diet' : '/diet';
  const dietHref = useMemo(() => {
    const params = new URLSearchParams();
    if (logDate) params.set('focus_date', logDate);
    if (mealType) params.set('focus_meal', mealType);
    const query = params.toString();
    return `${dietBase}${query ? `?${query}` : ''}#diet-week-progress`;
  }, [dietBase, logDate, mealType]);

  async function handleSubmit() {
    if (!token) {
      setError('请先登录后再记录。');
      return;
    }
    if (!resolvedSessionId) {
      setError('会话 ID 缺失，请刷新后重试。');
      return;
    }
    if (!logDate) {
      setError('请选择记录日期。');
      return;
    }
    if (!mealType) {
      setError('请选择餐次。');
      return;
    }
    if (!hasItems) {
      setError('未识别到食物明细，请补充描述或重新上传图片。');
      return;
    }

    setIsSubmitting(true);
    setError(null);
    try {
      const response = await applySmartAction(
        {
          session_id: resolvedSessionId,
          action_id: action.action_id,
          action_kind: 'create_diet_log',
          mode: 'user_select',
          payload: {
            log_date: logDate,
            meal_type: mealType,
            items: items.map((item) => ({
              food_name: item.food_name,
              weight_g: item.weight_g ?? undefined,
              unit: item.unit ?? undefined,
              calories: item.calories ?? undefined,
              protein: item.protein ?? undefined,
              fat: item.fat ?? undefined,
              carbs: item.carbs ?? undefined,
            })),
          },
        },
        token || undefined
      );

      setResult(response);

      // Auto-navigate so user immediately sees the record in diet management.
      if (!navigatedRef.current) {
        navigatedRef.current = true;
        navigate(dietHref);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '记录失败');
    } finally {
      setIsSubmitting(false);
    }
  }

  if (dismissed) {
    return (
      <div className="mt-3 rounded-xl border border-gray-200 dark:border-gray-700 bg-white/70 dark:bg-gray-900/40 p-3 text-xs text-gray-600 dark:text-gray-300">
        已选择不记录。本次不会写入饮食管理。
      </div>
    );
  }

  return (
    <div className="mt-3 rounded-xl border border-emerald-200 dark:border-emerald-800 bg-emerald-50/70 dark:bg-emerald-900/20 p-3">
      <div className="text-sm font-medium text-emerald-800 dark:text-emerald-200">
        {action.title || '确认记录本餐'}
      </div>
      {action.description && (
        <p className="mt-1 text-xs text-emerald-700 dark:text-emerald-300">{action.description}</p>
      )}

      <div className="mt-3 rounded-lg border border-emerald-100 dark:border-emerald-800/60 bg-white/80 dark:bg-gray-900/50 p-2.5">
        <div className="text-xs font-medium text-gray-800 dark:text-gray-200">识别结果（可在饮食管理里再编辑）</div>
        <div className="mt-2 space-y-1 text-xs text-gray-700 dark:text-gray-300">
          {hasItems ? (
            items.map((item, idx) => (
              <div key={idx} className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium">{item.food_name || '-'}</div>
                  <div className="mt-0.5 text-[11px] text-gray-500 dark:text-gray-400">
                    {item.weight_g ? `${item.weight_g} g` : item.unit ? item.unit : '分量未知'}
                    {item.calories ? ` · ${item.calories} kcal` : ''}
                  </div>
                </div>
                <div className="shrink-0 text-[11px] text-gray-500 dark:text-gray-400">
                  P {item.protein ?? '-'} · F {item.fat ?? '-'} · C {item.carbs ?? '-'}
                </div>
              </div>
            ))
          ) : (
            <div className="rounded-lg border border-amber-200/70 bg-amber-50/70 px-2.5 py-2 text-[11px] text-amber-800 dark:border-amber-900/60 dark:bg-amber-900/20 dark:text-amber-200">
              我还没识别到可写入的食物明细。你可以补充一句「我吃了什么 + 大概分量」，或重新上传图片后再点“记录本餐”。
            </div>
          )}
        </div>
        <div className="mt-2 rounded-lg border border-emerald-200/70 bg-emerald-50/60 px-2.5 py-2 text-xs text-emerald-700 dark:border-emerald-800 dark:bg-emerald-900/20 dark:text-emerald-200">
          合计 {totals.calories ? totals.calories.toFixed(0) : '-'} kcal · P {totals.protein.toFixed(1)} · F {totals.fat.toFixed(1)} · C {totals.carbs.toFixed(1)}
        </div>
      </div>

      <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-2">
        <div className="rounded-lg border border-emerald-100 dark:border-emerald-800/60 bg-white/80 dark:bg-gray-900/50 p-2.5">
          <div className="text-xs font-medium text-gray-800 dark:text-gray-200">日期</div>
          <input
            type="date"
            value={logDate}
            onChange={(e) => setLogDate(e.target.value)}
            className="mt-1 w-full rounded border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-2 py-1 text-xs text-gray-800 dark:text-gray-200"
          />
        </div>
        <div className="rounded-lg border border-emerald-100 dark:border-emerald-800/60 bg-white/80 dark:bg-gray-900/50 p-2.5">
          <div className="text-xs font-medium text-gray-800 dark:text-gray-200">餐次</div>
          <select
            value={mealType}
            onChange={(e) => setMealType(e.target.value)}
            className="mt-1 w-full rounded border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-2 py-1 text-xs text-gray-800 dark:text-gray-200"
          >
            {Object.keys(MEAL_LABELS).map((key) => (
              <option key={key} value={key}>
                {MEAL_LABELS[key]}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={handleSubmit}
          disabled={isSubmitting || !!result?.applied || !hasItems}
          className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isSubmitting ? '记录中...' : result?.applied ? '已记录' : '记录本餐'}
        </button>
        <button
          type="button"
          onClick={() => setDismissed(true)}
          disabled={isSubmitting}
          className="rounded-lg border border-gray-300 dark:border-gray-600 px-3 py-1.5 text-xs text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800"
        >
          不记录
        </button>
        {result?.applied && (
          <span className="inline-flex items-center gap-1 text-xs text-emerald-700 dark:text-emerald-300">
            <CheckCircle2 className="h-3.5 w-3.5" />
            {result.message || '已记录成功'}
          </span>
        )}
        {result?.applied && (
          <button
            type="button"
            onClick={() => navigate(dietHref)}
            className="rounded-lg border border-emerald-300 px-3 py-1.5 text-xs text-emerald-700 hover:bg-emerald-100 dark:border-emerald-700 dark:text-emerald-300 dark:hover:bg-emerald-900/30"
          >
            去饮食管理查看
          </button>
        )}
      </div>

      {error && (
        <div className="mt-2 inline-flex items-start gap-1.5 rounded-lg bg-red-50 dark:bg-red-900/30 px-2.5 py-2 text-xs text-red-600 dark:text-red-300">
          <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {isSubmitting && (
        <div className="mt-2 inline-flex items-center gap-1 text-xs text-emerald-700 dark:text-emerald-300">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          正在写入饮食记录...
        </div>
      )}
    </div>
  );
}
