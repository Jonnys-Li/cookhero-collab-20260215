/**
 * Agent Message Bubble Component
 * Displays individual chat messages with Agent-specific styling and trace rendering
 */

import { useState, useEffect, useRef } from 'react';
import { Clock, Loader2 } from 'lucide-react';
import type { Message } from '../../types';
import { MarkdownRenderer } from '../chat/MarkdownRenderer';
import { AgentThinkingBlock, type TraceStep } from './AgentThinkingBlock';
import { CopyButton } from '../common';

export interface AgentMessageBubbleProps {
  message: Message;
}

/**
 * Parse trace data from message - handles both string[] and object[]
 */
function parseTrace(trace: any[] | undefined): TraceStep[] {
  if (!trace || trace.length === 0) return [];
  
  return trace.map((item) => {
    // If it's already an object, use it directly
    if (typeof item === 'object' && item !== null) {
      return {
        error: item.error || null,
        action: item.action || item.type || 'unknown',
        content: item.content || null,
        iteration: item.iteration ?? 0,
        timestamp: item.timestamp || new Date().toISOString(),
        tool_calls: item.tool_calls,
      };
    }
    
    // If it's a string, try to parse it as JSON
    if (typeof item === 'string') {
      try {
        const parsed = JSON.parse(item);
        return {
          error: parsed.error || null,
          action: parsed.action || parsed.type || 'unknown',
          content: parsed.content || null,
          iteration: parsed.iteration ?? 0,
          timestamp: parsed.timestamp || new Date().toISOString(),
          tool_calls: parsed.tool_calls,
        };
      } catch {
        // If parsing fails, treat as content
        return {
          error: null,
          action: 'thinking',
          content: item,
          iteration: 0,
          timestamp: new Date().toISOString(),
          tool_calls: undefined,
        };
      }
    }
    
    return {
      error: null,
      action: 'unknown',
      content: String(item),
      iteration: 0,
      timestamp: new Date().toISOString(),
      tool_calls: undefined,
    };
  });
}

export function AgentMessageBubble({ message }: AgentMessageBubbleProps) {
  const isUser = message.role === 'user';
  const hasText = !!(message.content && message.content.trim().length > 0);
  
  // Parse trace data - use message.trace if available, otherwise fall back to message.thinking
  const traceData = parseTrace(message.trace || message.thinking);
  const hasTrace = traceData.length > 0;
  const isThinkingPhase = !isUser && !!message.isStreaming && !hasText;
  const showThinkingBlock = !isUser && (hasTrace || isThinkingPhase);

  // Handle both timestamp-based timing and duration-based timing
  const thinkingDuration = message.thinkingStartTime && message.thinkingEndTime
    ? message.thinkingEndTime - message.thinkingStartTime
    : (message as any).thinking_duration_ms || undefined;
  const answerDuration = message.answerStartTime && message.answerEndTime
    ? message.answerEndTime - message.answerStartTime
    : (message as any).answer_duration_ms || undefined;
  const totalDuration = message.thinkingStartTime && message.answerEndTime
    ? message.answerEndTime - message.thinkingStartTime
    : (thinkingDuration && answerDuration
        ? thinkingDuration + answerDuration
        : thinkingDuration || answerDuration || undefined);

  // Real-time elapsed time tracking for streaming
  const [elapsedTime, setElapsedTime] = useState(0);
  // Track when streaming started for this message - use useRef to persist across renders
  const streamStartTimeRef = useRef<number | undefined>(undefined);
  
  useEffect(() => {
    if (message.isStreaming) {
      // When streaming starts, record the start time if we don't have one
      if (!streamStartTimeRef.current && !message.thinkingStartTime && !message.answerStartTime) {
        streamStartTimeRef.current = Date.now();
      }
      
      const effectiveStartTime = message.thinkingStartTime || message.answerStartTime || streamStartTimeRef.current;
      if (!effectiveStartTime) return;
      
      // Update elapsed time every 100ms
      const interval = setInterval(() => {
        setElapsedTime(Date.now() - effectiveStartTime);
      }, 100);
      
      return () => clearInterval(interval);
    } else {
      // When streaming ends, reset the tracking
      streamStartTimeRef.current = undefined;
      setElapsedTime(0);
    }
  }, [message.isStreaming, message.thinkingStartTime, message.answerStartTime]);

  // Format duration for display
  const formatDuration = (ms: number) => {
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
  };

  return (
    <div className={`flex mb-6 ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`flex flex-col w-full ${
          isUser ? 'items-end' : 'items-start'
        }`}
      >
        {/* Thinking Block (Assistant only) - Show trace/execution steps */}
        {showThinkingBlock && (
          <div className="w-full mb-2">
            <AgentThinkingBlock 
              trace={traceData} 
              isThinking={isThinkingPhase} 
              thinkingDuration={thinkingDuration}
            />
          </div>
        )}

        {/* Message Text (hide while only thinking) */}
        {!isThinkingPhase && (
          <div
            className={`text-sm leading-relaxed break-words ${
              isUser
                ? 'bg-gradient-to-br from-blue-500 to-blue-500 text-white px-4 py-1 rounded-2xl shadow-sm'
                : 'prose prose-sm dark:prose-invert max-w-none text-gray-800 dark:text-gray-100 px-0 py-0'
            }`}
          >
            <MarkdownRenderer content={message.content.trim()} />
          </div>
        )}

        {/* Timestamp and Duration Stats */}
        <div
          className={`text-xs mt-2 flex items-center gap-2 flex-wrap ${
            isUser ? 'text-gray-500 dark:text-gray-400' : 'text-gray-600 dark:text-gray-400'
          }`}
        >
          {/* Copy button for user */}
          {hasText && isUser && (
            <CopyButton content={message.content.trim()} size="sm" />
          )}
          <span>
            {message.timestamp.toLocaleTimeString('zh-CN', {
              hour: '2-digit',
              minute: '2-digit',
            })}
          </span>
          
          {/* Real-time elapsed time during streaming */}
          {!isUser && message.isStreaming && elapsedTime > 0 && (
            <span className="inline-flex items-center gap-1 text-purple-500 dark:text-purple-400">
              <Loader2 className="w-3 h-3 animate-spin" />
              {formatDuration(elapsedTime)}
            </span>
          )}
          
          {/* Duration breakdown after completion */}
          {!isUser && !message.isStreaming && (thinkingDuration !== undefined || answerDuration !== undefined) && (
            <span className="inline-flex items-center gap-1">
              <Clock className="w-3 h-3" />
              {thinkingDuration !== undefined && answerDuration !== undefined ? (
                <span>
                  思考 {formatDuration(thinkingDuration)} · 生成 {formatDuration(answerDuration)}
                </span>
              ) : totalDuration !== undefined ? (
                <span>耗时 {formatDuration(totalDuration)}</span>
              ) : null}
            </span>
          )}
          
          {/* Copy button for assistant */}
          {hasText && !isUser && (
            <CopyButton content={message.content.trim()} size="sm" />
          )}
        </div>
      </div>
    </div>
  );
}
