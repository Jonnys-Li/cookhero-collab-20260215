import { useState, useEffect } from 'react';
import { ChevronDown, ChevronRight, Loader2 } from 'lucide-react';

interface ThinkingBlockProps {
  steps: string[];
  isThinking: boolean;
}

export function ThinkingBlock({ steps, isThinking }: ThinkingBlockProps) {
  const [isOpen, setIsOpen] = useState(true);
  const hasSteps = steps.length > 0;
  const shouldRender = hasSteps || isThinking;

  // Auto-collapse when thinking is done
  useEffect(() => {
    if (!isThinking) {
      setIsOpen(false);
    } else {
      setIsOpen(true);
    }
  }, [isThinking]);

  if (!shouldRender) return null;

  return (
    <div className="my-2 border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden bg-gray-50 dark:bg-gray-800/50">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between p-2 text-sm text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
      >
        <div className="flex items-center gap-2">
          {isThinking ? (
            <Loader2 className="w-4 h-4 animate-spin text-blue-500" />
          ) : (
            <div className="w-4 h-4" /> // Spacer
          )}
          <span className="font-medium">Thinking Process</span>
        </div>
        {isOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
      </button>
      
      {isOpen && steps.length > 0 && (
        <div className="p-3 text-sm text-gray-600 dark:text-gray-300 space-y-1 border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900/50">
          {(
            steps.map((step, index) => (
              <div key={`${step}-${index}`} className="flex items-start gap-2 animate-in fade-in slide-in-from-left-1 duration-300">
                <span className="text-gray-400 mt-0.5">•</span>
                <span>{step}</span>
              </div>
            ))
          )}
          {/* {isThinking && hasSteps && (
            <div className="flex items-center gap-2 text-gray-400 italic">
              <Loader2 className="w-3 h-3 animate-spin" />
              <span>生成中...</span>
            </div>
          )} */}
        </div>
      )}
    </div>
  );
}
