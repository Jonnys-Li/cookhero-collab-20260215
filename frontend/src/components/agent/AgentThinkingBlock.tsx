/**
 * Agent Thinking Block Component
 * Displays the AI agent execution trace with expandable steps
 */

import { useState, useEffect } from 'react';
import { ChevronDown, ChevronRight, Loader2, CheckCircle2, Cpu, AlertCircle, Clock, Play, ArrowRight } from 'lucide-react';

export interface TraceStep {
  error: string | null;
  action: string;
  content: string | number | boolean | object | null;
  iteration: number;
  timestamp: string;
  tool_calls?: {
    name: string;
    arguments: Record<string, unknown>;
  }[];
}

export interface AgentThinkingBlockProps {
  trace: TraceStep[];
  isThinking: boolean;
  thinkingDuration?: number; // Duration in milliseconds
  hasError?: boolean; // Whether an error occurred during thinking
}

export function AgentThinkingBlock({ trace, isThinking, thinkingDuration, hasError = false }: AgentThinkingBlockProps) {
  const [isOpen, setIsOpen] = useState(true);
  const hasSteps = trace.length > 0;

  // Filter out empty finish steps for display
  const displayableSteps = trace.filter((step) => {
    const isFinishType = step.action === 'finish' || step.action === 'final_answer';
    const hasToolCalls = step.tool_calls && step.tool_calls.length > 0;
    const hasError = !!step.error;
    if (isFinishType && !hasToolCalls && !hasError) {
      return false;
    }
    return true;
  });

  const hasDisplayableSteps = displayableSteps.length > 0;

  // Always render when thinking is done (to show "Response Completed")
  const shouldRender = hasSteps || isThinking || (!isThinking && thinkingDuration !== undefined);

  // Auto-collapse when thinking is done
  useEffect(() => {
    if (!isThinking) {
      setIsOpen(false);
    } else {
      setIsOpen(true);
    }
  }, [isThinking]);

  if (!shouldRender) return null;

  // Format duration for display
  const formatDuration = (ms: number) => {
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
  };

  // Get iteration count
  const iterations = trace.length > 0 ? Math.max(...trace.map(t => t.iteration)) + 1 : 0;

  return (
    <div className="my-2 border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden bg-gray-50 dark:bg-gray-800/50">
        <button
          onClick={() => setIsOpen(!isOpen)}
          className="w-full flex items-center justify-between p-2 text-sm text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          aria-expanded={isOpen}
          aria-controls="agent-trace-steps"
        >
          <div className="flex items-center gap-2">
            {isThinking ? (
              <Loader2 className="w-4 h-4 animate-spin text-purple-500" />
            ) : (
              <Cpu className="w-4 h-4 text-green-500" />
            )}
            <span className="font-medium">Thinking Process</span>
          {!isThinking && iterations > 0 && (
            <span className="text-xs text-gray-400 dark:text-gray-500">
              ({iterations} iteration{iterations > 1 ? 's' : ''})
            </span>
          )}
          {!isThinking && thinkingDuration !== undefined && !hasError && (
            <span className="text-xs text-gray-400 dark:text-gray-500 flex items-center gap-1">
              <Clock className="w-3 h-3" />
              {formatDuration(thinkingDuration)}
            </span>
          )}
        </div>
        {isOpen ? (
          <ChevronDown className="w-4 h-4" />
        ) : (
          <ChevronRight className="w-4 h-4" />
        )}
      </button>
      
        {isOpen && (
          <div
            id="agent-trace-steps"
            className="p-3 text-sm space-y-3 border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900"
          >
            {hasDisplayableSteps ? (
              displayableSteps.map((step, index) => (
                <TraceStepItem key={`${step.iteration}-${index}`} step={step} />
              ))
            ) : null}

            {/* Show "Thinking completed" when thinking is done, regardless of whether tool calls were made */}
            {!isThinking && (
              <div className="flex items-center gap-2 text-green-600 dark:text-green-400">
                <CheckCircle2 className="w-4 h-4" />
                <span className="text-sm">Thinking completed</span>
              </div>
            )}
          </div>
        )}
    </div>
  );
}

/**
 * Render a single trace step
 */
function TraceStepItem({ step }: { step: TraceStep }) {
  const hasToolCalls = step.tool_calls && step.tool_calls.length > 0;
  const hasError = !!step.error;
  const hasContent = step.content !== null && step.content !== undefined;
  const isToolResult = step.action === 'tool_result';

  // Determine icon and styling based on action type
  const getActionStyle = () => {
    if (hasError) {
      return {
        icon: <AlertCircle className="w-4 h-4 text-red-500" />,
        bgColor: 'bg-red-50 dark:bg-red-900/30',
        borderColor: 'border-red-200 dark:border-red-800',
        label: 'Error',
      };
    }
    if (step.action === 'tool_call') {
      return {
        icon: <Play className="w-4 h-4 text-amber-500" />,
        bgColor: 'bg-amber-50 dark:bg-amber-900/30',
        borderColor: 'border-amber-200 dark:border-amber-800',
        label: 'Tool Call',
      };
    }
    if (step.action === 'tool_result') {
      return {
        icon: <ArrowRight className="w-4 h-4 text-blue-500" />,
        bgColor: 'bg-blue-50 dark:bg-blue-900/30',
        borderColor: 'border-blue-200 dark:border-blue-800',
        label: 'Result',
      };
    }
    if (step.action === 'final_answer') {
      return {
        icon: <CheckCircle2 className="w-4 h-4 text-green-500" />,
        bgColor: 'bg-green-50 dark:bg-green-900/30',
        borderColor: 'border-green-200 dark:border-green-800',
        label: 'Complete',
      };
    }
    return {
      icon: <Cpu className="w-4 h-4 text-purple-500" />,
      bgColor: 'bg-purple-50 dark:bg-purple-900/30',
      borderColor: 'border-purple-200 dark:border-purple-800',
      label: step.action.replace(/_/g, ' '),
    };
  };

  const style = getActionStyle();

  // Format content for display
  const formatContent = (content: any): string => {
    if (content === null || content === undefined) return '';
    if (typeof content === 'string') return content;
    if (typeof content === 'object') {
      try {
        return JSON.stringify(content, null, 2);
      } catch {
        return String(content);
      }
    }
    return String(content);
  };

  return (
    <div className={`rounded-lg border ${style.borderColor} ${style.bgColor} p-2.5`}>
      {/* Header */}
      <div className="flex items-center gap-2">
        {style.icon}
        <span className="font-medium text-gray-700 dark:text-gray-300 text-sm">
          {style.label}
        </span>
        {hasToolCalls && step.tool_calls![0] && (
          <span className="text-xs font-mono text-gray-500 dark:text-gray-400 bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded">
            {step.tool_calls![0].name}
          </span>
        )}
      </div>

      {/* Tool call arguments */}
      {step.action === 'tool_call' && hasToolCalls && (
        <div className="mt-2">
          {step.tool_calls!.map((tool, idx) => {
            const hasArgs = tool.arguments && Object.keys(tool.arguments).length > 0;
            if (!hasArgs) return null;
            return (
              <pre key={idx} className="text-xs text-gray-600 dark:text-gray-400 overflow-x-auto whitespace-pre-wrap bg-white dark:bg-gray-800 rounded p-2 border border-gray-200 dark:border-gray-700">
                {JSON.stringify(tool.arguments, null, 2)}
              </pre>
            );
          })}
        </div>
      )}

      {/* Tool result content */}
      {isToolResult && hasContent && (
        <div className="mt-2 text-xs text-gray-600 dark:text-gray-400 bg-white dark:bg-gray-800 rounded p-2 border border-gray-200 dark:border-gray-700 overflow-x-auto">
          <pre className="whitespace-pre-wrap">{formatContent(step.content)}</pre>
        </div>
      )}

      {/* Other content - Don't show for final_answer/finish as it will be displayed as main message */}
      {hasContent && !isToolResult && step.action !== 'final_answer' && step.action !== 'finish' && (
        <div className="mt-2 text-gray-600 dark:text-gray-400 text-sm whitespace-pre-wrap">
          {formatContent(step.content)}
        </div>
      )}

      {/* Error */}
      {hasError && (
        <div className="mt-2 text-red-600 dark:text-red-400 text-xs bg-red-50 dark:bg-red-900/30 rounded p-2">
          {step.error}
        </div>
      )}
    </div>
  );
}
