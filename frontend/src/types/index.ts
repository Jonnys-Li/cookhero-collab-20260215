// src/types/index.ts
/**
 * Type definitions for CookHero frontend
 */

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  sources?: Source[];
  intent?: IntentInfo;
  isStreaming?: boolean;
  thinking?: string[];
}

export interface Source {
  type: string;
  info: string;
  title?: string;
  url?: string;
  category?: string;
}

export interface IntentInfo {
  need_rag: boolean;
  intent: string;
  reason: string;
}

export interface ConversationRequest {
  message: string;
  conversation_id?: string;
  stream?: boolean;
}

export interface SSEEvent {
  type: 'intent' | 'thinking' | 'text' | 'sources' | 'done';
  content?: string;
  data?: IntentInfo | Source[] | string;
  conversation_id?: string;
}

export interface Conversation {
  id: string;
  messages: Message[];
  createdAt: Date;
}

export interface ConversationSummary {
  id: string;
  title?: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  last_message_preview?: string | null;
}

export interface ConversationHistoryResponse {
  conversation_id: string;
  messages: Array<{
    role: 'user' | 'assistant';
    content: string;
    timestamp: string;
    sources?: Source[];
    intent?: IntentInfo;
    thinking?: string[];
  }>;
}

export interface Credentials {
  username: string;
  password: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  username: string;
}

export interface UserProfile {
  username: string;
  occupation?: string | null;
  bio?: string | null;
}
