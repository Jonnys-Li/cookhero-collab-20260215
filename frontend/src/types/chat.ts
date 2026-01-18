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
  // Timing information for response tracking
  thinkingStartTime?: number; // Unix timestamp in ms when thinking started
  thinkingEndTime?: number;   // Unix timestamp in ms when thinking ended
  answerStartTime?: number;   // Unix timestamp in ms when answer generation started
  answerEndTime?: number;     // Unix timestamp in ms when answer generation ended
  // Image attachments (base64 encoded)
  images?: string[];
  // Vision analysis result
  vision?: VisionInfo;
  
  // Agent specific fields
  agent_session_id?: string;
  trace?: any[]; // Agent execution trace
  tool_calls?: any[]; // Tool calls made by agent
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

/**
 * Vision analysis result from image processing.
 */
export interface VisionInfo {
  is_food_related: boolean;
  intent: string;
  description: string;
  extracted_info?: {
    dish_name?: string;
    ingredients?: string[];
    cooking_stage?: string;
    other?: string;
  };
  direct_response?: string;
  confidence: number;
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

export interface AgentChatRequest {
  message: string;
  session_id?: string;
  agent_name?: string;
  stream?: boolean;
  selected_tools?: string[];  // User-selected tools
}

export interface ToolSchema {
  name: string;
  description: string;
}

export interface ServerInfo {
  name: string;
  type: 'local' | 'mcp';
  tools: ToolSchema[];
}

export interface ToolsListResponse {
  servers: ServerInfo[];
}

export interface AgentSessionResponse {
  id: string;
  user_id: string;
  title?: string | null;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface AgentMessageResponse {
  id: string;
  session_id: string;
  role: string;
  content: string;
  created_at: string;
  trace?: any[];
  thinking_duration_ms?: number;
  answer_duration_ms?: number;
}

export interface AgentSessionListResponse {
  sessions: AgentSessionResponse[];
  total_count: number;
  limit: number;
  offset: number;
}

export interface AgentHistoryResponse {
  session_id: string;
  messages: AgentMessageResponse[];
}

// Streaming state for conversation caching
export interface StreamingState {
  conversationId: string;
  messages: Message[];
  isStreaming: boolean;
  tempId?: string;
}
