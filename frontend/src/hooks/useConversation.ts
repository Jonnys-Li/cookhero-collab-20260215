// src/hooks/useConversation.ts
/**
 * Custom hook for managing conversation state
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import type {
  Message,
  IntentInfo,
  Source,
  ConversationSummary,
  ConversationHistoryResponse,
} from '../types';
import {
  deleteConversation,
  getConversationHistory,
  listConversations,
  streamConversation,
  updateConversationTitle,
} from '../services/api';

function generateId(): string {
  return Date.now().toString(36) + Math.random().toString(36).substr(2);
}

// Use setTimeout instead of requestAnimationFrame to avoid browser throttling in background tabs
const waitForNextTick = () =>
  new Promise<void>((resolve) => {
    setTimeout(resolve, 0);
  });

// Type for streaming state cache
interface StreamingState {
  conversationId: string;
  messages: Message[];
  isStreaming: boolean;
}

export function useConversation(token?: string) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [conversationId, setConversationId] = useState<string | undefined>();
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [totalConversations, setTotalConversations] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  
  // Pagination state
  const [conversationOffset, setConversationOffset] = useState(0);
  const [hasMoreConversations, setHasMoreConversations] = useState(true);
  const CONVERSATIONS_PAGE_SIZE = 30;
  
  // Cache for streaming state when switching conversations
  const streamingCacheRef = useRef<Map<string, StreamingState>>(new Map());

  const refreshConversations = useCallback(async (reset = true) => {
    try {
      const { conversations: list, total_count } = await listConversations(
        token,
        CONVERSATIONS_PAGE_SIZE,
        reset ? 0 : conversationOffset,
      );
      
      if (reset) {
        setConversations(list);
        setConversationOffset(CONVERSATIONS_PAGE_SIZE);
      } else {
        setConversations(prev => [...prev, ...list]);
        setConversationOffset(prev => prev + CONVERSATIONS_PAGE_SIZE);
      }
      
      setTotalConversations(total_count);
      setHasMoreConversations((reset ? 0 : conversationOffset) + list.length < total_count);
    } catch (err) {
      console.error('Failed to list conversations:', err);
    }
  }, [token]); // Remove conversationOffset from dependencies

  const loadMoreConversations = useCallback(async () => {
    if (!hasMoreConversations) return;
    await refreshConversations(false);
  }, [hasMoreConversations, refreshConversations]);

  // Initial load only when token changes
  useEffect(() => {
    if (token) {
      // Reset pagination and load first page
      setConversationOffset(0);
      setHasMoreConversations(true);
      listConversations(token, CONVERSATIONS_PAGE_SIZE, 0)
        .then(({ conversations: list, total_count }) => {
          setConversations(list);
          setConversationOffset(CONVERSATIONS_PAGE_SIZE);
          setTotalConversations(total_count);
          setHasMoreConversations(list.length < total_count);
        })
        .catch(err => console.error('Failed to list conversations:', err));
    } else {
      setConversations([]);
      setTotalConversations(0);
    }
  }, [token]);

  const mapHistoryToMessages = useCallback(
    (history: ConversationHistoryResponse['messages']): Message[] => {
      return history.map((msg, idx) => ({
        id: `${msg.timestamp}-${idx}`,
        role: msg.role,
        content: msg.content,
        timestamp: new Date(msg.timestamp),
        sources: msg.sources,
        intent: msg.intent,
        thinking: msg.thinking,
      }));
    },
    []
  );

  const sendMessage = useCallback(async (content: string) => {
    if (!content.trim() || isLoading) return;
    if (!token) {
      setError('Please log in to start chatting.');
      return;
    }

    setError(null);
    setIsLoading(true);
    setIsStreaming(true);

    // Create abort controller for this request
    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    // Add user message
    const userMessage: Message = {
      id: generateId(),
      role: 'user',
      content: content.trim(),
      timestamp: new Date(),
    };
    setMessages(prev => [...prev, userMessage]);

    // Create assistant message placeholder (no content until LLM starts streaming)
    const assistantMessageId = generateId();
    const assistantMessage: Message = {
      id: assistantMessageId,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      isStreaming: true,
    };
    setMessages(prev => [...prev, assistantMessage]);

    // Track the conversation ID for this streaming session
    let streamingConvId = conversationId;

    // Helper to update cache
    const updateCache = (newMessages: Message[], streaming: boolean) => {
      if (streamingConvId) {
        streamingCacheRef.current.set(streamingConvId, {
          conversationId: streamingConvId,
          messages: newMessages,
          isStreaming: streaming,
        });
      }
    };

    try {
      let currentContent = '';
      let currentIntent: IntentInfo | undefined;
      let currentSources: Source[] = [];
      let currentThinking: string[] = [];

      for await (const event of streamConversation({
        message: content,
        conversation_id: conversationId,
      }, token, abortController.signal)) {
        // Check if aborted
        if (abortController.signal.aborted) {
          break;
        }

        switch (event.type) {
          case 'intent':
            currentIntent = event.data as IntentInfo;
            setMessages(prev => {
              const updated = prev.map(msg =>
                msg.id === assistantMessageId
                  ? { ...msg, intent: currentIntent }
                  : msg
              );
              updateCache(updated, true);
              return updated;
            });
            break;

          case 'thinking':
            {
              const thought = event.content || (typeof event.data === 'string' ? event.data : '');
              if (thought) {
                currentThinking = [...currentThinking, thought];
                setMessages(prev => {
                  const updated = prev.map(msg =>
                    msg.id === assistantMessageId
                      ? { ...msg, thinking: currentThinking }
                      : msg
                  );
                  updateCache(updated, true);
                  return updated;
                });
              }
            }
            break;

          case 'text':
            currentContent += event.content || '';
            setMessages(prev => {
              const updated = prev.map(msg =>
                msg.id === assistantMessageId
                  ? { ...msg, content: currentContent }
                  : msg
              );
              updateCache(updated, true);
              return updated;
            });
            break;

          case 'sources':
            currentSources = event.data as Source[];
            setMessages(prev => {
              const updated = prev.map(msg =>
                msg.id === assistantMessageId
                  ? { ...msg, sources: currentSources }
                  : msg
              );
              updateCache(updated, true);
              return updated;
            });
            break;

          case 'done':
            if (event.conversation_id) {
              streamingConvId = event.conversation_id;
              setConversationId(event.conversation_id);
              refreshConversations();
            }
            setMessages(prev => {
              const updated = prev.map(msg =>
                msg.id === assistantMessageId
                  ? { ...msg, isStreaming: false }
                  : msg
              );
              // Clear cache when streaming is done
              if (streamingConvId) {
                streamingCacheRef.current.delete(streamingConvId);
              }
              return updated;
            });
            break;
        }

        await waitForNextTick();
      }

      // Mark streaming as complete even if loop finished without 'done' event
      setMessages(prev => {
        const updated = prev.map(msg =>
          msg.id === assistantMessageId
            ? { ...msg, isStreaming: false }
            : msg
        );
        // Clear cache when streaming is done
        if (streamingConvId) {
          streamingCacheRef.current.delete(streamingConvId);
        }
        return updated;
      });
    } catch (err) {
      // Don't show error if it was an abort
      if (err instanceof Error && err.name === 'AbortError') {
        // Mark the message as stopped
        setMessages(prev =>
          prev.map(msg =>
            msg.id === assistantMessageId
              ? { ...msg, isStreaming: false, content: msg.content || '(Generation stopped)' }
              : msg
          )
        );
      } else {
        console.error('Failed to send message:', err);
        setError(err instanceof Error ? err.message : 'Failed to send message');
        
        // Remove the failed assistant message
        setMessages(prev => prev.filter(msg => msg.id !== assistantMessageId));
      }
    } finally {
      setIsLoading(false);
      setIsStreaming(false);
      abortControllerRef.current = null;
    }
  }, [conversationId, isLoading, refreshConversations, token]);
  
  const selectConversation = useCallback(async (id: string) => {
    if (!id) return;
    
    // Check if we have cached streaming state for this conversation
    const cachedState = streamingCacheRef.current.get(id);
    if (cachedState) {
      // Restore from cache - streaming is still in progress
      setConversationId(cachedState.conversationId);
      setMessages(cachedState.messages);
      setIsStreaming(cachedState.isStreaming);
      return;
    }
    
    setIsLoading(true);
    setError(null);
    try {
      const history = await getConversationHistory(id, token);
      setConversationId(history.conversation_id);
      setMessages(mapHistoryToMessages(history.messages));
    } catch (err) {
      console.error('Failed to load conversation:', err);
      setError(err instanceof Error ? err.message : 'Failed to load conversation');
    } finally {
      setIsLoading(false);
    }
  }, [mapHistoryToMessages, token]);

  const clearMessages = useCallback(() => {
    setMessages([]);
    setConversationId(undefined);
    setError(null);
  }, []);

  const removeConversation = useCallback(async (id: string) => {
    if (!id || !token) return false;
    try {
      await deleteConversation(id, token);
      // Refresh the entire conversation list from server
      await refreshConversations(true);
      // If we're viewing the deleted conversation, clear it
      if (conversationId === id) {
        setMessages([]);
        setConversationId(undefined);
      }
      return true;
    } catch (err) {
      console.error('Failed to delete conversation:', err);
      setError(err instanceof Error ? err.message : 'Failed to delete conversation');
      return false;
    }
  }, [conversationId, token, refreshConversations]);

  const renameConversation = useCallback(async (id: string, newTitle: string) => {
    if (!id || !token) return false;
    try {
      await updateConversationTitle(id, newTitle, token);
      // Update local state
      setConversations(prev =>
        prev.map(conv =>
          conv.id === id ? { ...conv, title: newTitle } : conv
        )
      );
      return true;
    } catch (err) {
      console.error('Failed to rename conversation:', err);
      setError(err instanceof Error ? err.message : 'Failed to rename conversation');
      return false;
    }
  }, [token]);

  const stopGeneration = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsLoading(false);
    
    // Mark any streaming messages as complete
    setMessages(prev =>
      prev.map(msg =>
        msg.isStreaming ? { ...msg, isStreaming: false } : msg
      )
    );
  }, []);

  return {
    messages,
    conversationId,
    conversations,
    totalConversations,
    hasMoreConversations,
    isLoading,
    isStreaming,
    error,
    sendMessage,
    selectConversation,
    refreshConversations,
    loadMoreConversations,
    clearMessages,
    stopGeneration,
    removeConversation,
    renameConversation,
  };
}
