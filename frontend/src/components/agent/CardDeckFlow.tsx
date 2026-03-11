import { useEffect, useMemo, useState } from 'react';

import type { CollabTimelineAction, EmotionBudgetUIAction, SmartRecommendationAction } from '../../types';
import type { TraceStep } from './AgentThinkingBlock';
import { AgentCollabTimelineCard } from './AgentCollabTimelineCard';
import { EmotionBudgetAdjustCard } from './EmotionBudgetAdjustCard';
import { SmartRecommendationCard } from './SmartRecommendationCard';

type DeckStep =
  | { kind: 'emotion_budget_adjust'; action: EmotionBudgetUIAction }
  | { kind: 'smart_next_meal'; action: SmartRecommendationAction }
  | { kind: 'smart_review_relax'; action: SmartRecommendationAction };

function getStepPreview(step: DeckStep): { title: string; subtitle: string; tone: string } {
  if (step.kind === 'emotion_budget_adjust') {
    return {
      title: '情绪预算调整',
      subtitle: '先完成预算动作，再继续后续建议',
      tone: 'border-orange-200/70 bg-orange-50/70 dark:border-orange-900/50 dark:bg-orange-900/10',
    };
  }
  if (step.kind === 'smart_next_meal') {
    return {
      title: '下一餐纠偏',
      subtitle: '写入下一餐计划，降低当日负担',
      tone: 'border-violet-200/70 bg-violet-50/70 dark:border-violet-900/50 dark:bg-violet-900/10',
    };
  }
  return {
    title: '周进度与放松',
    subtitle: '查看偏差并给出放松建议',
    tone: 'border-sky-200/70 bg-sky-50/70 dark:border-sky-900/50 dark:bg-sky-900/10',
  };
}

function parseEmotionBudgetAction(trace: TraceStep[]): EmotionBudgetUIAction | null {
  const reversed = [...trace].reverse();
  for (const step of reversed) {
    if (step.action !== 'ui_action') continue;
    if (!step.content || typeof step.content !== 'object') continue;
    const payload = step.content as Record<string, unknown>;
    if (payload.action_type !== 'emotion_budget_adjust') continue;
    if (!payload.action_id) continue;
    return payload as unknown as EmotionBudgetUIAction;
  }
  return null;
}

function parseSmartRecommendationAction(trace: TraceStep[]): SmartRecommendationAction | null {
  const reversed = [...trace].reverse();
  for (const step of reversed) {
    if (step.action !== 'ui_action') continue;
    if (!step.content || typeof step.content !== 'object') continue;
    const payload = step.content as Record<string, unknown>;
    if (payload.action_type !== 'smart_recommendation_card') continue;
    if (!payload.action_id) continue;
    return payload as unknown as SmartRecommendationAction;
  }
  return null;
}

function parseCollabTimelineAction(trace: TraceStep[]): CollabTimelineAction | null {
  const reversed = [...trace].reverse();
  for (const step of reversed) {
    if (step.action !== 'collab_timeline') continue;
    if (!step.content || typeof step.content !== 'object') continue;
    const payload = step.content as Record<string, unknown>;
    if (payload.action_type !== 'collab_timeline') continue;
    return payload as unknown as CollabTimelineAction;
  }
  return null;
}

function buildDeck(trace: TraceStep[]): DeckStep[] {
  const deck: DeckStep[] = [];

  const emotion = parseEmotionBudgetAction(trace);
  if (emotion) {
    deck.push({ kind: 'emotion_budget_adjust', action: emotion });
  }

  const smart = parseSmartRecommendationAction(trace);
  if (smart) {
    deck.push({ kind: 'smart_next_meal', action: smart });
    deck.push({ kind: 'smart_review_relax', action: smart });
  }

  return deck;
}

function firstUnresolvedIndex(deck: DeckStep[], trace: TraceStep[]): number {
  // If backend already persisted result trace steps, fast-forward deck index.
  // We only care about per-step completion markers:
  // - emotion_budget_adjust_result
  // - smart_action_result: apply_next_meal_plan
  // - smart_action_result: fetch_weekly_progress
  const traceItems = [...trace].reverse();
  const hasEmotionResult = traceItems.some((s) => s.action === 'emotion_budget_adjust_result');
  const hasNextMealResult = traceItems.some((s) => {
    if (s.action !== 'smart_action_result') return false;
    if (!s.content || typeof s.content !== 'object') return false;
    return String((s.content as any).action_kind || '') === 'apply_next_meal_plan';
  });
  const hasWeeklyResult = traceItems.some((s) => {
    if (s.action !== 'smart_action_result') return false;
    if (!s.content || typeof s.content !== 'object') return false;
    return String((s.content as any).action_kind || '') === 'fetch_weekly_progress';
  });

  for (let i = 0; i < deck.length; i += 1) {
    const step = deck[i];
    if (step.kind === 'emotion_budget_adjust') {
      if (!hasEmotionResult) return i;
      continue;
    }
    if (step.kind === 'smart_next_meal') {
      if (!hasNextMealResult) return i;
      continue;
    }
    if (step.kind === 'smart_review_relax') {
      if (!hasWeeklyResult) return i;
      continue;
    }
  }

  // all resolved or no actionable steps
  return Math.max(0, deck.length - 1);
}

export function CardDeckFlow({
  trace,
  sessionId,
}: {
  trace: TraceStep[];
  sessionId?: string;
}) {
  const collab = useMemo(() => parseCollabTimelineAction(trace), [trace]);
  const deck = useMemo(() => buildDeck(trace), [trace]);
  const [activeIndex, setActiveIndex] = useState(() => firstUnresolvedIndex(deck, trace));
  const [transitioning, setTransitioning] = useState(false);

  useEffect(() => {
    setActiveIndex(firstUnresolvedIndex(deck, trace));
  }, [deck, trace]);

  const active = deck[activeIndex];
  if (!active && !collab) return null;

  const stackTail = deck.slice(activeIndex + 1);
  const stackCount = stackTail.length;

  const advance = () => {
    if (transitioning) return;
    setTransitioning(true);
    window.setTimeout(() => {
      setActiveIndex((prev) => Math.min(prev + 1, deck.length - 1));
      setTransitioning(false);
    }, 240);
  };

  return (
    <div className="mt-3">
      {collab && <AgentCollabTimelineCard timeline={collab} />}
      <div className={`transition-all duration-200 ${transitioning ? 'opacity-40 translate-y-1' : 'opacity-100 translate-y-0'}`}>
        {active?.kind === 'emotion_budget_adjust' && (
          <EmotionBudgetAdjustCard
            action={active.action}
            trace={trace}
            sessionId={sessionId || active.action.session_id}
            onStepResolved={() => advance()}
            showSkipButton
          />
        )}
        {active?.kind === 'smart_next_meal' && (
          <SmartRecommendationCard
            action={active.action}
            trace={trace}
            sessionId={sessionId || active.action.session_id}
            mode="next_meal"
            onStepResolved={() => advance()}
            showSkipButton
          />
        )}
        {active?.kind === 'smart_review_relax' && (
          <SmartRecommendationCard
            action={active.action}
            trace={trace}
            sessionId={sessionId || active.action.session_id}
            mode="review_relax"
            onStepResolved={() => advance()}
            showSkipButton
          />
        )}
      </div>

      {stackCount > 0 && (
        <div className="mt-3">
          <div className="text-[11px] text-gray-500 dark:text-gray-400">后续步骤（逐张抽取）</div>
          <div className="relative mt-1 h-[88px]">
            {stackTail.slice(0, 3).map((step, idx) => {
              const preview = getStepPreview(step);
              const depth = idx;
              return (
                <div
                  key={`${step.kind}-${idx}`}
                  className={`absolute inset-x-0 rounded-xl border p-2 shadow-sm transition-all ${preview.tone}`}
                  style={{
                    transform: `translateY(${depth * 10}px) scale(${1 - depth * 0.02})`,
                    opacity: 1 - depth * 0.16,
                    zIndex: stackTail.length - idx,
                  }}
                >
                  <div className="text-xs font-medium text-gray-700 dark:text-gray-200">{preview.title}</div>
                  <div className="mt-0.5 text-[11px] text-gray-500 dark:text-gray-400">{preview.subtitle}</div>
                </div>
              );
            })}
          </div>
          <div className="text-[11px] text-gray-500 dark:text-gray-400">
            共 {stackCount} 步待处理
          </div>
        </div>
      )}
    </div>
  );
}
