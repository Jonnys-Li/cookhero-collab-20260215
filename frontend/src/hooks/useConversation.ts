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
import { STORAGE_KEYS, CONVERSATIONS_PAGE_SIZE } from '../constants';
import { generateId, waitForNextTick } from '../utils';

// Type for streaming state cache
interface StreamingState {
  conversationId: string;
  messages: Message[];
  isStreaming: boolean;
  tempId?: string; // present when a new conversation hasn't received a server id yet
}

// Helper functions for localStorage streaming cache
const saveStreamingCache = (cache: Map<string, StreamingState>) => {
  try {
    const data = Array.from(cache.entries());
    localStorage.setItem(STORAGE_KEYS.STREAMING_CACHE, JSON.stringify(data));
  } catch (e) {
    console.warn('Failed to save streaming cache to localStorage:', e);
  }
};

const loadStreamingCache = (): Map<string, StreamingState> => {
  try {
    const data = localStorage.getItem(STORAGE_KEYS.STREAMING_CACHE);
    if (!data) return new Map();
    const entries = JSON.parse(data) as Array<[string, StreamingState]>;
    // Restore Date objects in messages
    return new Map(
      entries.map(([key, state]) => [
        key,
        {
          ...state,
          messages: state.messages.map(msg => ({
            ...msg,
            timestamp: new Date(msg.timestamp),
          })),
        },
      ])
    );
  } catch (e) {
    console.warn('Failed to load streaming cache from localStorage:', e);
    return new Map();
  }
};

const clearStreamingCache = (conversationId?: string) => {
  try {
    if (conversationId) {
      const cache = loadStreamingCache();
      cache.delete(conversationId);
      saveStreamingCache(cache);
    } else {
      localStorage.removeItem(STORAGE_KEYS.STREAMING_CACHE);
    }
  } catch (e) {
    console.warn('Failed to clear streaming cache:', e);
  }
};

export function useConversation(token?: string) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [conversationId, setConversationId] = useState<string | undefined>();
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [totalConversations, setTotalConversations] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  
  // Track whether abort was triggered by user switching conversations vs stopping generation
  const abortReasonRef = useRef<'switch' | 'stop' | null>(null);
  
  // Pagination state
  const [conversationOffset, setConversationOffset] = useState(0);
  const [hasMoreConversations, setHasMoreConversations] = useState(true);
  
  // Cache for streaming state when switching conversations
  // Initialize from localStorage if available
  const streamingCacheRef = useRef<Map<string, StreamingState>>(loadStreamingCache());
  
  // Ref for refreshConversations to avoid stale closure in sendMessage
  const refreshConversationsRef = useRef<((reset?: boolean) => Promise<void>) | null>(null);

  const refreshConversations = useCallback(
    async (reset = true) => {
      try {
        const nextOffset = reset ? 0 : conversationOffset;
        const { conversations: list, total_count } = await listConversations(
          token,
          CONVERSATIONS_PAGE_SIZE,
          nextOffset,
        );

        if (reset) {
          setConversations(list);
          setConversationOffset(CONVERSATIONS_PAGE_SIZE);
        } else {
          setConversations(prev => [...prev, ...list]);
          setConversationOffset(prev => prev + CONVERSATIONS_PAGE_SIZE);
        }

        setTotalConversations(total_count);
        setHasMoreConversations(nextOffset + list.length < total_count);
      } catch (err) {
        console.error('Failed to list conversations:', err);
      }
    },
    [conversationOffset, token]
  );
  
  // Update ref whenever refreshConversations changes
  useEffect(() => {
    refreshConversationsRef.current = refreshConversations;
  }, [refreshConversations]);

  // Separate function for initial load to avoid circular dependency
  const initialLoadConversations = useCallback(async () => {
    try {
      const { conversations: list, total_count } = await listConversations(
        token,
        CONVERSATIONS_PAGE_SIZE,
        0,
      );
      setConversations(list);
      setConversationOffset(CONVERSATIONS_PAGE_SIZE);
      setTotalConversations(total_count);
      setHasMoreConversations(list.length < total_count);
    } catch (err) {
      console.error('Failed to list conversations:', err);
    }
  }, [token]);

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
      initialLoadConversations();
    } else {
      setConversations([]);
      setTotalConversations(0);
    }
  }, [token, initialLoadConversations]);

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

    // Track the conversation ID for this streaming session
    // If we don't have a server conversation yet, create a provisional id so switching works
    let streamingConvId = conversationId ?? `temp-${assistantMessageId}`;
    const isTempConversation = !conversationId;

    // Add assistant placeholder and seed cache immediately so switching before first token is safe
    setMessages(prev => {
      const next = [...prev, assistantMessage];
      streamingCacheRef.current.set(streamingConvId, {
        conversationId: streamingConvId,
        messages: next,
        isStreaming: true,
        tempId: isTempConversation ? streamingConvId : undefined,
      });
      // Also persist to localStorage immediately
      saveStreamingCache(streamingCacheRef.current);
      return next;
    });

    // If this is a brand-new conversation, insert a provisional entry so it appears in the list
    if (isTempConversation) {
      setConversationId(streamingConvId);
      setConversations(prev => {
        // Avoid duplicates
        if (prev.find(c => c.id === streamingConvId)) return prev;
        return [
          {
            id: streamingConvId,
            title: 'New Conversation',
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            message_count: 0,
            last_message_preview: content.slice(0, 50),
          },
          ...prev,
        ];
      });
    }

    // Helper to update cache
    const updateCache = (newMessages: Message[], streaming: boolean) => {
      if (streamingConvId) {
        const existing = streamingCacheRef.current.get(streamingConvId);
        const updatedState = {
          conversationId: streamingConvId,
          messages: newMessages,
          isStreaming: streaming,
          tempId: existing?.tempId ?? (isTempConversation ? streamingConvId : undefined),
        };
        streamingCacheRef.current.set(streamingConvId, updatedState);
        // Persist to localStorage
        saveStreamingCache(streamingCacheRef.current);
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
              const newId = event.conversation_id;
              // Move cache entry from temp to real id
              if (isTempConversation && streamingConvId !== newId) {
                const cached = streamingCacheRef.current.get(streamingConvId);
                if (cached) {
                  streamingCacheRef.current.delete(streamingConvId);
                  streamingCacheRef.current.set(newId, { ...cached, conversationId: newId, tempId: streamingConvId });
                }
                // Replace provisional conversation list entry
                setConversations(prev =>
                  prev.map(c => (c.id === streamingConvId ? { ...c, id: newId } : c))
                );
              }
              streamingConvId = newId;
              setConversationId(newId);
              refreshConversationsRef.current?.(true);
            }
            setMessages(prev => {
              const updated = prev.map(msg =>
                msg.id === assistantMessageId
                  ? { ...msg, isStreaming: false }
                  : msg
              );
              return updated;
            });
            // Clear cache when streaming is done
            if (streamingConvId) {
              streamingCacheRef.current.delete(streamingConvId);
              clearStreamingCache(streamingConvId);
            }
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
        return updated;
      });
      // Clear cache when streaming is done
      if (streamingConvId) {
        streamingCacheRef.current.delete(streamingConvId);
        clearStreamingCache(streamingConvId);
      }
    } catch (err) {
      // Don't show error if it was an abort
      if (err instanceof Error && err.name === 'AbortError') {
        const reason = abortReasonRef.current;
        abortReasonRef.current = null;
        
        if (reason === 'switch') {
          // User switched to another conversation - preserve cache as-is for potential return
          // Don't modify the cache content, just mark streaming as stopped
          if (streamingConvId) {
            const cached = streamingCacheRef.current.get(streamingConvId);
            if (cached) {
              // Preserve current content, just mark as not streaming
              const updatedMessages = cached.messages.map(msg =>
                msg.id === assistantMessageId
                  ? { ...msg, isStreaming: false }
                  : msg
              );
              streamingCacheRef.current.set(streamingConvId, {
                ...cached,
                messages: updatedMessages,
                isStreaming: false,
              });
              saveStreamingCache(streamingCacheRef.current);
            }
          }
          // Don't update local messages state since user has switched away
        } else {
          // User explicitly stopped generation - update UI to show stopped state
          setMessages(prev =>
            prev.map(msg =>
              msg.id === assistantMessageId
                ? { ...msg, isStreaming: false, content: msg.content || '(Generation stopped)' }
                : msg
            )
          );
          // Clear cache since user stopped it explicitly
          if (streamingConvId) {
            streamingCacheRef.current.delete(streamingConvId);
            clearStreamingCache(streamingConvId);
          }
        }
      } else {
        console.error('Failed to send message:', err);
        setError(err instanceof Error ? err.message : 'Failed to send message');
        
        // Remove the failed assistant message
        setMessages(prev => prev.filter(msg => msg.id !== assistantMessageId));
        
        // Clear cache on real error
        if (streamingConvId) {
          streamingCacheRef.current.delete(streamingConvId);
          clearStreamingCache(streamingConvId);
          // Also remove temp conversation from list
          if (isTempConversation) {
            setConversations(prev => prev.filter(c => c.id !== streamingConvId));
          }
        }
      }
    } finally {
      setIsLoading(false);
      setIsStreaming(false);
      abortControllerRef.current = null;
    }
  }, [conversationId, isLoading, token]);
  
  const selectConversation = useCallback(async (id: string) => {
    if (!id) return;
    
    // Abort any ongoing streaming request before switching
    if (abortControllerRef.current) {
      abortReasonRef.current = 'switch';
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    
    // Reset streaming state immediately when switching
    setIsStreaming(false);
    setIsLoading(false);
    
    // Check if we have cached streaming state for this conversation
    const cachedState = streamingCacheRef.current.get(id);
    if (cachedState) {
      // Restore from cache - streaming may still be in progress
      setConversationId(cachedState.conversationId);
      setMessages(cachedState.messages);
      setIsStreaming(cachedState.isStreaming);
      return;
    }
    
    // Check if this is a temporary ID (not yet created on server)
    // These IDs start with 'temp-'
    if (id.startsWith('temp-')) {
      // This is a temp conversation that hasn't been saved yet
      // Just clear the view - the conversation doesn't exist on server
      setConversationId(undefined);
      setMessages([]);
      setError('This conversation has not been saved yet.');
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
    // Abort any ongoing streaming request
    if (abortControllerRef.current) {
      abortReasonRef.current = 'switch';
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setMessages([]);
    setConversationId(undefined);
    setError(null);
    setIsStreaming(false);
  }, []);

  const removeConversation = useCallback(async (id: string) => {
    if (!id || !token) return false;
    
    // Handle temp conversations (not yet saved to server)
    if (id.startsWith('temp-')) {
      // Just remove from local state
      streamingCacheRef.current.delete(id);
      clearStreamingCache(id);
      setConversations(prev => prev.filter(c => c.id !== id));
      if (conversationId === id) {
        setMessages([]);
        setConversationId(undefined);
      }
      return true;
    }
    
    try {
      await deleteConversation(id, token);
      // Clear cache for this conversation
      streamingCacheRef.current.delete(id);
      clearStreamingCache(id);
      // Refresh the entire conversation list from server
      await initialLoadConversations();
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
  }, [conversationId, token, initialLoadConversations]);

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
      abortReasonRef.current = 'stop';
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsLoading(false);
    setIsStreaming(false);
    
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
