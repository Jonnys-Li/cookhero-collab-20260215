import { useState } from 'react';
import { CheckCircle2, ChevronDown, ChevronRight, CircleDashed, Loader2, SkipForward, TriangleAlert } from 'lucide-react';

import type { CollabTimelineAction, CollabTimelineStage } from '../../types';

interface AgentCollabTimelineCardProps {
  timeline: CollabTimelineAction;
}

function getStageStyle(stage: CollabTimelineStage) {
  switch (stage.status) {
    case 'completed':
      return {
        icon: <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />,
        badge: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300',
        label: '已完成',
      };
    case 'running':
      return {
        icon: <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-500" />,
        badge: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300',
        label: '执行中',
      };
    case 'failed':
      return {
        icon: <TriangleAlert className="h-3.5 w-3.5 text-red-500" />,
        badge: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300',
        label: '失败',
      };
    case 'skipped':
      return {
        icon: <SkipForward className="h-3.5 w-3.5 text-gray-500" />,
        badge: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300',
        label: '跳过',
      };
    default:
      return {
        icon: <CircleDashed className="h-3.5 w-3.5 text-amber-500" />,
        badge: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',
        label: '待执行',
      };
  }
}

export function AgentCollabTimelineCard({ timeline }: AgentCollabTimelineCardProps) {
  const [isOpen, setIsOpen] = useState(false);
  if (!timeline.stages?.length) return null;

  return (
    <div className="mt-3 rounded-xl border border-indigo-200 dark:border-indigo-800 bg-indigo-50/70 dark:bg-indigo-900/20 p-3">
      <button
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        className="w-full flex items-center justify-between text-left"
      >
        <span className="text-sm font-medium text-indigo-800 dark:text-indigo-200">
          三系统协作时间线
        </span>
        {isOpen ? (
          <ChevronDown className="h-4 w-4 text-indigo-500" />
        ) : (
          <ChevronRight className="h-4 w-4 text-indigo-500" />
        )}
      </button>
      {isOpen && (
        <div className="mt-2 space-y-2">
          {timeline.stages.map((stage) => {
            const style = getStageStyle(stage);
            return (
              <div
                key={stage.id}
                className="rounded-lg border border-indigo-100 dark:border-indigo-800/60 bg-white/70 dark:bg-gray-900/50 px-2.5 py-2"
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="inline-flex items-center gap-2 text-xs text-gray-700 dark:text-gray-200">
                    {style.icon}
                    <span className="font-medium">{stage.label}</span>
                  </div>
                  <span className={`rounded-full px-2 py-0.5 text-[11px] ${style.badge}`}>
                    {style.label}
                  </span>
                </div>
                {(stage.summary || stage.reason) && (
                  <div className="mt-1 text-[11px] text-gray-600 dark:text-gray-400">
                    {stage.summary || stage.reason}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
