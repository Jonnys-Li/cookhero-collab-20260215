/**
 * API-related type definitions
 */

import type { IntentInfo, Source, VisionInfo } from './chat';

/** Image data for multimodal requests */
export interface ImageData {
  data: string;  // Base64 encoded image data
  mime_type: string;  // MIME type of the image
}

/** Extra options that can be enabled per request */
export interface ExtraOptions {
  web_search?: boolean;
  // Future extensibility
  // deep_reasoning?: boolean;
  // multimodal?: boolean;
}

export interface ConversationRequest {
  message: string;
  conversation_id?: string;
  stream?: boolean;
  extra_options?: ExtraOptions;
  images?: ImageData[];  // Images for multimodal understanding
}

export interface SSEEvent {
  type: 'vision' | 'intent' | 'thinking' | 'text' | 'sources' | 'done' | 'session' | 'tool_call' | 'tool_result' | 'trace' | 'ui_action' | 'collab_timeline' | 'skill_load' | 'error';
  content?: string;
  data?: VisionInfo | IntentInfo | Source[] | string;
  conversation_id?: string;
  // Agent-specific fields
  session_id?: string;
  title?: string;
  // Tool call fields
  id?: string;
  name?: string;
  arguments?: Record<string, unknown>;
  iteration?: number;
  action?: string;
  tool_calls?: Array<{ name: string; arguments: Record<string, unknown> }>;
  source?: 'agent' | 'subagent';
  subagent_name?: string;
  // Tool result fields
  success?: boolean;
  result?: unknown;
  error?: string;
  // UI action fields (emotion support)
  action_id?: string;
  action_type?: string;
  timeout_seconds?: number;
  default_delta_calories?: number;
  can_apply?: boolean;
  unavailable_reason?: string | null;
  stages?: Array<{ id: string; label: string; status: string; reason?: string; summary?: string }>;
  // Timing fields
  thinking_duration_ms?: number;
  answer_duration_ms?: number;
}

export interface ConversationListResponse {
  conversations: import('./chat').ConversationSummary[];
  total_count: number;
  limit: number;
  offset: number;
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
    thinking_duration_ms?: number;
    answer_duration_ms?: number;
  }>;
}

export interface ApiError {
  detail: string | Array<{ loc: string[]; msg: string; type: string }>;
  message?: string;
}

export interface CapabilitiesResponse {
  api_version?: string;
  community_ai_modes?: string[];
}
