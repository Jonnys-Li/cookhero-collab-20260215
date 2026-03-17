// src/pages/chat/ChatView.tsx
import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { AgentChatInput, AgentChatWindow, ChatInput, ChatWindow } from '../../components';
import { useAuth } from '../../contexts';
import { useChat } from '../../hooks/useChat';

function AgentChatPane({
  chat,
  suggestionText,
  onSuggestionClick,
  onSuggestionConsumed,
  token,
}: {
  chat: Extract<ReturnType<typeof useChat>, { mode: 'agent' }>;
  suggestionText: string;
  onSuggestionClick: (text: string) => void;
  onSuggestionConsumed: () => void;
  token?: string;
}) {
  const [isToolSelectorOpen, setIsToolSelectorOpen] = useState(false);

  return (
    <>
      <AgentChatWindow
        messages={chat.messages}
        isLoading={chat.isLoading}
        onSuggestionClick={onSuggestionClick}
        error={chat.error}
        isToolSelectorOpen={isToolSelectorOpen}
      />
      <div className="p-4 max-w-4xl w-full mx-auto">
        <AgentChatInput
          onSend={chat.sendMessage}
          onCancel={chat.stopGeneration}
          disabled={chat.isLoading}
          isStreaming={chat.isStreaming}
          placeholder="Ask Agent to calculate, analyze, or plan..."
          externalValue={suggestionText}
          onExternalValueConsumed={onSuggestionConsumed}
          token={token}
          onToolsOpenChange={setIsToolSelectorOpen}
        />
        <div className="text-center text-xs text-gray-400 mt-2">
          CookHero Agent can make mistakes. Consider checking important information.
        </div>
      </div>
    </>
  );
}

/**
 * Chat view component - handles both new chat and existing conversation/session.
 */
export default function ChatView() {
  const { id: urlThreadId } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const { token } = useAuth();
  const chat = useChat();
  const { basePath, selectThread, threadId } = chat;

  const [suggestionText, setSuggestionText] = useState<string>('');

  // Track if we've done initial sync to avoid re-triggering on subsequent renders
  const initialSyncDone = useRef(false);

  // Sync URL conversation ID with hook state on mount or when URL changes
  useEffect(() => {
    // Only sync from URL to state, not the other way around
    if (urlThreadId && urlThreadId !== threadId) {
      selectThread(urlThreadId);
    }
    initialSyncDone.current = true;
  }, [selectThread, threadId, urlThreadId]);

  // Update URL when a NEW conversation is created (temp -> real ID)
  useEffect(() => {
    if (
      initialSyncDone.current &&
      threadId &&
      !threadId.startsWith('temp-') &&
      !urlThreadId // Only update URL if we're on /chat or /agent (no ID in URL yet)
    ) {
      navigate(`${basePath}/${threadId}`, { replace: true });
    }
  }, [basePath, navigate, threadId, urlThreadId]);

  const handleSuggestionClick = (text: string) => {
    setSuggestionText(text);
  };

  const handleSuggestionConsumed = () => {
    setSuggestionText('');
  };

  return (
    <>
      {chat.error && (
        <div className="absolute top-4 left-4 right-4 z-10 p-3 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-lg text-red-600 dark:text-red-400 text-sm">
          {chat.error}
        </div>
      )}

      {chat.mode === 'agent' ? (
        <AgentChatPane
          chat={chat}
          suggestionText={suggestionText}
          onSuggestionClick={handleSuggestionClick}
          onSuggestionConsumed={handleSuggestionConsumed}
          token={token || undefined}
        />
      ) : (
        <>
          <ChatWindow
            messages={chat.messages}
            isLoading={chat.isLoading}
            onSuggestionClick={handleSuggestionClick}
            error={chat.error}
          />
          <div className="p-4 max-w-4xl w-full mx-auto">
            <ChatInput
              onSend={chat.sendMessage}
              onCancel={chat.stopGeneration}
              disabled={chat.isLoading}
              isStreaming={chat.isStreaming}
              placeholder="Ask CookHero anything about health..."
              externalValue={suggestionText}
              onExternalValueConsumed={handleSuggestionConsumed}
            />
            <div className="text-center text-xs text-gray-400 mt-2">
              CookHero can make mistakes. Consider checking important information.
            </div>
          </div>
        </>
      )}
    </>
  );
}
