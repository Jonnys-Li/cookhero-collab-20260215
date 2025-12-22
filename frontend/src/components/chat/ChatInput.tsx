/**
 * Chat Input Component
 * Text area with send button, cancel functionality for streaming, and optional features toggle
 */

import { useState, useRef, useEffect, type KeyboardEvent } from 'react';
import { SendHorizontal, Square, Globe } from 'lucide-react';

/** Extra options that can be enabled per message */
export interface ExtraOptions {
  web_search?: boolean;
  // Future extensibility
  // deep_reasoning?: boolean;
  // multimodal?: boolean;
}

export interface ChatInputProps {
  onSend: (message: string, extraOptions?: ExtraOptions) => void;
  onCancel?: () => void;
  disabled?: boolean;
  isStreaming?: boolean;
  placeholder?: string;
  externalValue?: string;
  onExternalValueConsumed?: () => void;
}

export function ChatInput({ 
  onSend, 
  onCancel,
  disabled = false, 
  isStreaming = false,
  placeholder = 'Type a message...', 
  externalValue,
  onExternalValueConsumed,
}: ChatInputProps) {
  const [input, setInput] = useState('');
  const [isComposing, setIsComposing] = useState(false);
  const [webSearchEnabled, setWebSearchEnabled] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Handle external value (from SuggestionChip)
  useEffect(() => {
    if (externalValue !== undefined && externalValue !== '') {
      setInput(externalValue);
      onExternalValueConsumed?.();
      // Focus the textarea
      textareaRef.current?.focus();
    }
  }, [externalValue, onExternalValueConsumed]);

  const handleSend = () => {
    if (input.trim() && !disabled && !isStreaming) {
      const extraOptions: ExtraOptions = {};
      if (webSearchEnabled) {
        extraOptions.web_search = true;
      }
      onSend(input, Object.keys(extraOptions).length > 0 ? extraOptions : undefined);
      setInput('');
      
      // Reset textarea height
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
    }
  };

  const handleCancel = () => {
    onCancel?.();
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !isComposing) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    
    // Auto-resize textarea
    const textarea = e.target;
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px';
  };

  const canSend = input.trim() && !disabled && !isStreaming;

  return (
    <div className="relative">
      {/* Feature toggles row */}
      <div className="flex items-center gap-2 mb-2">
        <button
          onClick={() => setWebSearchEnabled(!webSearchEnabled)}
          className={`
            inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium
            transition-all duration-200 border
            ${webSearchEnabled
              ? 'bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 border-blue-200 dark:border-blue-800'
              : 'bg-gray-50 dark:bg-gray-800 text-gray-500 dark:text-gray-400 border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-700'
            }
          `}
          title={webSearchEnabled ? 'Web Search enabled' : 'Enable Web Search'}
          aria-label={webSearchEnabled ? 'Disable Web Search' : 'Enable Web Search'}
        >
          <Globe className="w-3.5 h-3.5" />
          <span>Web Search</span>
          {webSearchEnabled && (
            <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse" />
          )}
        </button>
      </div>
      
      {/* Input area */}
      <div className="relative flex items-end gap-2 p-3 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl shadow-sm focus-within:ring-2 focus-within:ring-blue-500/20 focus-within:border-blue-500 transition-all">
        <textarea
          ref={textareaRef}
          value={input}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          onCompositionStart={() => setIsComposing(true)}
          onCompositionEnd={() => setIsComposing(false)}
          placeholder={placeholder}
          rows={1}
          className="flex-1 max-h-[200px] py-2 px-2 bg-transparent border-none focus:ring-0 resize-none text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 text-sm leading-relaxed scrollbar-hide"
        />
        {isStreaming ? (
          <button
            onClick={handleCancel}
            className="p-2 rounded-lg transition-all duration-200 bg-red-500 text-white hover:bg-red-600 shadow-sm"
            title="Stop generating"
            aria-label="Stop generating"
          >
            <Square className="w-5 h-5" />
          </button>
        ) : (
          <button
            onClick={handleSend}
            disabled={!canSend}
            className={`
              p-2 rounded-lg transition-all duration-200
              ${canSend
                ? 'bg-blue-500 text-white hover:bg-blue-600 shadow-sm'
                : 'bg-gray-100 dark:bg-gray-700 text-gray-400 dark:text-gray-500 cursor-not-allowed'
              }
            `}
            aria-label="Send message"
          >
            <SendHorizontal className="w-5 h-5" />
          </button>
        )}
      </div>
    </div>
  );
}
