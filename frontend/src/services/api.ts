// src/services/api.ts
/**
 * API service for communicating with CookHero backend
 */

import type {
  AuthResponse,
  ConversationHistoryResponse,
  ConversationRequest,
  ConversationSummary,
  Credentials,
  SSEEvent,
} from '../types';

const API_BASE = '/api/v1';

const authHeaders = (token?: string): HeadersInit | undefined =>
  token ? { Authorization: `Bearer ${token}` } : undefined;

/**
 * Send a message and receive streaming response
 */
export async function* streamConversation(
  request: ConversationRequest,
  token?: string,
  signal?: AbortSignal
): AsyncGenerator<SSEEvent> {
  const response = await fetch(`${API_BASE}/conversation`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      ...request,
      stream: true,
    }),
    signal,
  });

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error('No response body');
  }

  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      // Check if aborted before reading
      if (signal?.aborted) {
        break;
      }

      const { done, value } = await reader.read();
      
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      
      // Process complete SSE events
      const lines = buffer.split('\n');
      buffer = lines.pop() || ''; // Keep incomplete line in buffer

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6));
            yield data as SSEEvent;
          } catch (e) {
            console.warn('Failed to parse SSE event:', line);
          }
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

/**
 * Get conversation history
 */
export async function getConversationHistory(
  conversationId: string,
  token?: string
): Promise<ConversationHistoryResponse> {
  const response = await fetch(`${API_BASE}/conversation/${conversationId}`, {
    headers: authHeaders(token),
  });

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }

  return response.json();
}

/**
 * List conversations with pagination
 */
export async function listConversations(
  token?: string,
  limit: number = 50,
  offset: number = 0,
): Promise<{ conversations: ConversationSummary[]; total_count: number }> {
  const params = new URLSearchParams({
    limit: limit.toString(),
    offset: offset.toString(),
  });
  const response = await fetch(`${API_BASE}/conversation?${params}`, {
    headers: authHeaders(token),
  });

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }

  return response.json();
}

/**
 * Clear a conversation
 */
export async function clearConversation(conversationId: string, token?: string) {
  const response = await fetch(`${API_BASE}/conversation/${conversationId}`, {
    method: 'DELETE',
    headers: authHeaders(token),
  });
  
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }
  
  return response.json();
}

/**
 * Delete a conversation
 */
export async function deleteConversation(conversationId: string, token?: string) {
  const response = await fetch(`${API_BASE}/conversation/${conversationId}`, {
    method: 'DELETE',
    headers: authHeaders(token),
  });
  
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }
  
  return response.json();
}

/**
 * Update conversation title
 */
export async function updateConversationTitle(
  conversationId: string,
  title: string,
  token?: string
) {
  const response = await fetch(`${API_BASE}/conversation/${conversationId}/title`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ title }),
  });
  
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }
  
  return response.json();
}

export async function loginUser(credentials: Credentials): Promise<AuthResponse> {
  const response = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(credentials),
  });

  if (!response.ok) {
    const msg = await parseErrorResponse(response);
    throw new Error(msg || 'Invalid username or password');
  }

  return response.json();
}

export async function registerUser(credentials: Credentials): Promise<AuthResponse> {
  const response = await fetch(`${API_BASE}/auth/register`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(credentials),
  });

  if (!response.ok) {
    const msg = await parseErrorResponse(response);
    throw new Error(msg || 'Failed to register');
  }

  return response.json();
}

export async function getProfile(token?: string) {
  const response = await fetch(`${API_BASE}/auth/me`, {
    headers: authHeaders(token),
  });

  if (!response.ok) {
    const msg = await parseErrorResponse(response);
    throw new Error(msg || 'Failed to fetch profile');
  }

  return response.json();
}

export async function updateProfile(data: Partial<{ username: string; occupation: string; bio: string }>, token?: string) {
  const response = await fetch(`${API_BASE}/auth/me`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      ...(authHeaders(token) as Record<string, string>),
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    const msg = await parseErrorResponse(response);
    throw new Error(msg || 'Failed to update profile');
  }

  return response.json();
}

/**
 * Parse typical FastAPI error responses (Pydantic validation errors or HTTPException)
 * and return a friendly message string. If multiple field errors are present,
 * join them with newlines.
 */
async function parseErrorResponse(response: Response): Promise<string> {
  const ct = response.headers.get('content-type') || '';
  try {
    if (ct.includes('application/json')) {
      const body = await response.json();

      // Pydantic validation errors use `detail` as an array of error objects
      if (Array.isArray(body.detail)) {
        const parts = body.detail.map((err: any) => {
          const loc = Array.isArray(err.loc) ? err.loc.filter(Boolean) : [];
          // try to pick useful field name from loc (skip 'body')
          const field = loc.length ? loc[loc.length - 1] : 'field';
          const msg = typeof err.msg === 'string' ? err.msg : JSON.stringify(err.msg);
          // Nice formatting: capitalize field name
          return `${capitalize(String(field))}: ${friendlyMessageFor(msg, err.ctx)}
`.trim();
        });
        return parts.join('\n');
      }

      // If detail is a string, return it
      if (typeof body.detail === 'string') {
        return body.detail;
      }

      // Fallback to message or stringified body
      if (body.message) return String(body.message);
      return JSON.stringify(body);
    }
    // Not JSON; return raw text
    return await response.text();
  } catch (e) {
    return String(e instanceof Error ? e.message : 'Unknown error');
  }
}

function capitalize(s: string) {
  if (!s) return s;
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function friendlyMessageFor(msg: string, ctx?: any) {
  // Try to normalize Pydantic style messages like "String should have at least 6 characters"
  if (msg.includes('at least') && ctx && ctx.min_length) {
    return `Must be at least ${ctx.min_length} characters`;
  }
  // common explicit translation
  if (msg.includes('field required') || msg === 'value_error.missing') {
    return 'This field is required';
  }
  return msg;
}
