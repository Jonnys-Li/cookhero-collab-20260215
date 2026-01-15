
import { API_BASE } from '../../constants';
import { createAuthHeaders, createJsonHeaders, parseErrorResponse } from './client';
import type {
  AgentChatRequest,
  AgentSessionListResponse,
  AgentHistoryResponse,
  SSEEvent,
  AgentSessionResponse
} from '../../types';

/**
 * Send a message to the Agent and receive streaming response
 */
export async function* streamAgentChat(
  request: AgentChatRequest,
  token?: string,
  signal?: AbortSignal
): AsyncGenerator<SSEEvent> {
  const response = await fetch(`${API_BASE}/agent/chat`, {
    method: 'POST',
    headers: createJsonHeaders(token),
    body: JSON.stringify({
      ...request,
      stream: true,
    }),
    signal,
  });

  if (!response.ok) {
    const msg = await parseErrorResponse(response);
    throw new Error(msg || `HTTP error! status: ${response.status}`);
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error('No response body');
  }

  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      if (signal?.aborted) break;

      const { done, value } = await reader.read();
      
      if (done) {
        if (buffer.trim()) {
          const remainingLines = buffer.split('\n');
          for (const line of remainingLines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6));
                yield data as SSEEvent;
              } catch (e) {
                console.warn('Failed to parse final SSE event:', line);
              }
            }
          }
        }
        break;
      }

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

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
    try {
      await reader.cancel();
    } catch { }
    reader.releaseLock();
  }
}

/**
 * List agent sessions
 */
export async function listAgentSessions(
  token?: string,
  limit: number = 50,
  offset: number = 0,
  agentName?: string
): Promise<AgentSessionListResponse> {
  const params = new URLSearchParams({
    limit: limit.toString(),
    offset: offset.toString(),
  });
  if (agentName) params.append('agent_name', agentName);
  
  const response = await fetch(`${API_BASE}/agent/sessions?${params}`, {
    headers: createAuthHeaders(token),
  });

  if (!response.ok) {
    const msg = await parseErrorResponse(response);
    throw new Error(msg || `HTTP error! status: ${response.status}`);
  }

  return response.json();
}

/**
 * Get agent session history
 */
export async function getAgentSessionHistory(
  sessionId: string,
  token?: string
): Promise<AgentHistoryResponse> {
  const response = await fetch(`${API_BASE}/agent/session/${sessionId}/messages`, {
    headers: createAuthHeaders(token),
  });

  if (!response.ok) {
    const msg = await parseErrorResponse(response);
    throw new Error(msg || `HTTP error! status: ${response.status}`);
  }

  return response.json();
}

/**
 * Delete agent session
 */
export async function deleteAgentSession(
  sessionId: string,
  token?: string
): Promise<{ message: string }> {
  const response = await fetch(`${API_BASE}/agent/session/${sessionId}`, {
    method: 'DELETE',
    headers: createAuthHeaders(token),
  });
  
  if (!response.ok) {
    const msg = await parseErrorResponse(response);
    throw new Error(msg || `HTTP error! status: ${response.status}`);
  }
  
  return response.json();
}

/**
 * Get single agent session details
 */
export async function getAgentSession(
    sessionId: string,
    token?: string
): Promise<AgentSessionResponse> {
    const response = await fetch(`${API_BASE}/agent/session/${sessionId}`, {
        headers: createAuthHeaders(token),
    });

    if (!response.ok) {
        const msg = await parseErrorResponse(response);
        throw new Error(msg || `HTTP error! status: ${response.status}`);
    }

    return response.json();
}

/**
 * Update agent session title
 */
export async function updateAgentSessionTitle(
    sessionId: string,
    title: string,
    token?: string
): Promise<{ message: string; title: string }> {
    const response = await fetch(`${API_BASE}/agent/session/${sessionId}/title`, {
        method: 'PATCH',
        headers: createJsonHeaders(token),
        body: JSON.stringify({ title }),
    });

    if (!response.ok) {
        const msg = await parseErrorResponse(response);
        throw new Error(msg || `HTTP error! status: ${response.status}`);
    }

    return response.json();
}
