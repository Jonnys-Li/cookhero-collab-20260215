/**
 * Chat-related type definitions
 */

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  sources?: Source[];
  intent?: IntentInfo | string;
  isStreaming?: boolean;
  thinking?: string[];
}

/**
 * Unified source structure for both RAG and Web search results.
 * 
 * @property type - "rag" for knowledge base, "web" for web search
 * @property info - Display text describing the source
 * @property url - Optional URL (primarily for web sources, clickable link)
 */
export interface Source {
  type: 'rag' | 'web' | string;
  info: string;
  url?: string;
}

export interface IntentInfo {
  need_rag: boolean;
  intent: string;
  reason: string;
}

export interface ConversationSummary {
  id: string;
  title?: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  last_message_preview?: string | null;
}

export interface Conversation {
  id: string;
  messages: Message[];
  createdAt: Date;
}

// Streaming state for conversation caching
export interface StreamingState {
  conversationId: string;
  messages: Message[];
  isStreaming: boolean;
  tempId?: string;
}
