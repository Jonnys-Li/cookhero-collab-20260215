// src/components/ChatInput.tsx
/**
 * Chat input component with send button and cancel functionality
 */

import { useState, useRef, useEffect, type KeyboardEvent } from 'react';
import { SendHorizontal, Square } from 'lucide-react';

interface ChatInputProps {
  onSend: (message: string) => void;
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
      onSend(input);
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
    if (e.key === 'Enter' && !e.shiftKey) {
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
      <div className="relative flex items-end gap-2 p-3 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl shadow-sm focus-within:ring-2 focus-within:ring-blue-500/20 focus-within:border-blue-500 transition-all">
        <textarea
          ref={textareaRef}
          value={input}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          rows={1}
          className="flex-1 max-h-[200px] py-2 px-2 bg-transparent border-none focus:ring-0 resize-none text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 text-sm leading-relaxed scrollbar-hide"
        />
        {isStreaming ? (
          <button
            onClick={handleCancel}
            className="p-2 rounded-lg transition-all duration-200 bg-red-500 text-white hover:bg-red-600 shadow-sm"
            title="Stop generating"
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
          >
            <SendHorizontal className="w-5 h-5" />
          </button>
        )}
      </div>
    </div>
  );
}
