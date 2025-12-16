// src/components/MessageBubble.tsx
/**
 * Message bubble component for displaying chat messages
 */

import { Search, MessageCircle, Loader2 } from 'lucide-react';
import type { Message } from '../types';
import { MarkdownRenderer } from './MarkdownRenderer';
import { ThinkingBlock } from './ThinkingBlock';

interface MessageBubbleProps {
  message: Message;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user';
  const hasText = !!(message.content && message.content.trim().length > 0);
  const thinkingSteps = message.thinking ?? [];
  const hasThinkingSteps = thinkingSteps.length > 0;
  const isThinkingPhase = !isUser && !!message.isStreaming && !hasText;
  const showThinkingBlock = !isUser && (hasThinkingSteps || isThinkingPhase);
  // message.intent may be a string (e.g. 'recipe_search') or an object (legacy).
  const rawIntent: string | undefined = (() => {
    if (!message.intent) return undefined;
    if (typeof message.intent === 'string') return message.intent;
    if (typeof message.intent === 'object' && 'intent' in message.intent) return (message.intent as any).intent;
    return undefined;
  })();

  const intentLabelMap: Record<string, string> = {
    recipe_search: '菜谱搜索',
    cooking_tips: '烹饪技巧',
    ingredient_info: '食材信息',
    recommendation: '菜品推荐',
    general_chat: '闲聊',
  };

  return (
    <div className={`flex mb-6 ${isUser ? 'justify-end' : 'justify-start'}`}>

      {/* Content */}
      <div className={`flex flex-col max-w-[85%] ${isUser ? 'items-end self-end' : 'items-start self-start'}`}>
        {/* Intent Indicator (Assistant only, name removed) */}
        <div className="flex items-center gap-2 mb-1.5">
          {!isUser && rawIntent && (
            <div className="flex items-center">
              {rawIntent === 'general_chat' ? (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400 text-xs font-medium border border-blue-200 dark:border-blue-800">
                  <MessageCircle className="w-3 h-3" />
                  直接回复
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400 text-xs font-medium border border-green-200 dark:border-green-800">
                  <Search className="w-3 h-3" />
                  {`知识库检索 · ${intentLabelMap[rawIntent] ?? rawIntent}`}
                </span>
              )}
            </div>
          )}
        </div>

        {/* Thinking Block (Assistant only) */}
        {showThinkingBlock && (
          <div className="w-full mb-2">
            <ThinkingBlock 
              steps={thinkingSteps} 
              isThinking={isThinkingPhase} 
            />
          </div>
        )}

        {/* Spinner placeholder before text is ready */}
        {!isUser && isThinkingPhase && (
          <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400 mb-2">
            <Loader2 className="w-4 h-4 animate-spin text-orange-500" />
            <span>AI 正在准备回答...</span>
          </div>
        )}

        {/* Message Text (hide while only thinking) */}
        {isThinkingPhase ? null : (
          <div className={`text-sm leading-relaxed ${isUser ? 'bg-gradient-to-br from-blue-500 to-blue-500 text-white px-4 py-1 rounded-2xl shadow-sm' : 'prose prose-sm dark:prose-invert max-w-none text-gray-800 dark:text-gray-100 px-0 py-0'}`}>
            <MarkdownRenderer content={message.content.trim()} />
          </div>
        )}

        {/* Sources (Assistant only) */}
        {!isUser && message.sources && message.sources.length > 0 && (
          <div className="mt-3 w-full">
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-1.5 font-medium">📚 参考来源：</p>
            <ul className="space-y-1">
              {message.sources.map((source, idx) => (
                <li 
                  key={idx}
                  className="text-xs text-gray-600 dark:text-gray-400 flex items-center gap-2"
                >
                  <span className="w-1.5 h-1.5 rounded-full bg-orange-400 shrink-0" />
                  <span>{source.info}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Timestamp */}
        <div className={`text-xs mt-2 ${isUser ? 'text-blue-200' : 'text-gray-400 dark:text-gray-500'}`}>
          {message.timestamp.toLocaleTimeString('zh-CN', {
            hour: '2-digit',
            minute: '2-digit',
          })}
        </div>
      </div>
    </div>
  );
}
