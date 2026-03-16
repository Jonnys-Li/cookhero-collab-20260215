// src/hooks/useChat.ts
/**
 * Unified chat/agent selector hook for the App shell.
 *
 * This does NOT attempt to merge the underlying implementations of `useConversation`
 * and `useAgent` yet. Instead it provides a single discriminated union API so views
 * (ChatView, MainLayout, etc.) can avoid duplicating "agent vs chat" branching logic.
 */

import { useLocation } from 'react-router-dom';
import type { ConversationSummary, ExtraOptions, ImageData, Message } from '../types';
import { useAgentContext, useConversationContext } from '../contexts';

export type ChatMode = 'chat' | 'agent';

type BaseUnifiedChat = {
  mode: ChatMode;
  isAgentMode: boolean;
  basePath: string;

  threadId?: string;
  messages: Message[];
  isLoading: boolean;
  isStreaming: boolean;
  error: string | null;
  stopGeneration: () => void;

  threads: ConversationSummary[];
  totalThreads: number;
  hasMoreThreads: boolean;
  loadMoreThreads: () => Promise<void>;
  selectThread: (id: string) => void;
  clearThread: () => void;
  removeThread: (id: string) => Promise<boolean>;
  renameThread: (id: string, newTitle: string) => Promise<boolean>;
};

export type UnifiedChat =
  | (BaseUnifiedChat & {
      mode: 'chat';
      sendMessage: (message: string, extraOptions?: ExtraOptions, images?: ImageData[]) => void;
    })
  | (BaseUnifiedChat & {
      mode: 'agent';
      sendMessage: (message: string, selectedTools?: string[], images?: ImageData[]) => void;
    });

export function useChat(): UnifiedChat {
  const location = useLocation();
  const isAgentMode = location.pathname.startsWith('/agent');
  const basePath = isAgentMode ? '/agent' : '/chat';

  // Both hooks must be called unconditionally (rules of hooks).
  const conversation = useConversationContext();
  const agent = useAgentContext();

  if (isAgentMode) {
    const threads: ConversationSummary[] = agent.sessions.map((s) => ({
      id: s.id,
      title: s.title ?? undefined,
      created_at: s.created_at,
      updated_at: s.updated_at,
      message_count: s.message_count,
      last_message_preview: s.last_message_preview,
    }));

    return {
      mode: 'agent',
      isAgentMode: true,
      basePath,
      threadId: agent.sessionId,
      messages: agent.messages,
      isLoading: agent.isLoading,
      isStreaming: agent.isStreaming,
      error: agent.error,
      sendMessage: agent.sendMessage,
      stopGeneration: agent.stopGeneration,
      threads,
      totalThreads: agent.totalSessions,
      hasMoreThreads: agent.hasMoreSessions,
      loadMoreThreads: agent.loadMoreSessions,
      selectThread: agent.selectSession,
      clearThread: agent.clearMessages,
      removeThread: agent.removeSession,
      renameThread: agent.renameSession,
    };
  }

  return {
    mode: 'chat',
    isAgentMode: false,
    basePath,
    threadId: conversation.conversationId,
    messages: conversation.messages,
    isLoading: conversation.isLoading,
    isStreaming: conversation.isStreaming,
    error: conversation.error,
    sendMessage: conversation.sendMessage,
    stopGeneration: conversation.stopGeneration,
    threads: conversation.conversations,
    totalThreads: conversation.totalConversations,
    hasMoreThreads: conversation.hasMoreConversations,
    loadMoreThreads: conversation.loadMoreConversations,
    selectThread: conversation.selectConversation,
    clearThread: conversation.clearMessages,
    removeThread: conversation.removeConversation,
    renameThread: conversation.renameConversation,
  };
}

