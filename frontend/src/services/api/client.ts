/**
 * Base API client with common utilities
 */

import { API_BASE, STORAGE_KEYS } from '../../constants';
import { capitalize } from '../../utils';

const DEFAULT_TIMEOUT_MS = 12000;
const API_TIMEOUT_MS = Number(import.meta.env.VITE_API_TIMEOUT_MS || DEFAULT_TIMEOUT_MS);
// Default fallback base:
// - In production, call Render direct as a safety valve for Vercel rewrite drift.
// - In local dev, we must NOT default to cross-origin Render because Vite proxies
//   `/api/*` to the local backend (and mixing backends invalidates JWTs, causing
//   "login expired" behavior).
const DEFAULT_FALLBACK_BASE = import.meta.env.DEV
  ? ''
  : 'https://cookhero-collab-20260215.onrender.com/api/v1';
const API_FALLBACK_BASE =
  import.meta.env.VITE_API_FALLBACK_BASE || DEFAULT_FALLBACK_BASE;
const RETRYABLE_STATUS_CODES = new Set([429, 500, 502, 503, 504]);

type RequestOptions = {
  timeoutMs?: number;
  /**
   * If true, prefer calling API_FALLBACK_BASE first (Render direct) and use API_BASE
   * as the fallback. This is useful for write operations because Vercel rewrite may
   * fail with ROUTER_EXTERNAL_TARGET_ERROR.
   */
  preferFallback?: boolean;
};

function normalizeBase(base: string): string {
  return base.endsWith('/') ? base.slice(0, -1) : base;
}

function normalizeEndpoint(endpoint: string): string {
  return endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
}

function buildRequestUrl(base: string, endpoint: string): string {
  return `${normalizeBase(base)}${normalizeEndpoint(endpoint)}`;
}

function getFallbackUrl(endpoint: string): string | null {
  const normalizedPrimary = normalizeBase(API_BASE);
  const normalizedFallback = normalizeBase(API_FALLBACK_BASE);

  if (!normalizedFallback || normalizedFallback === normalizedPrimary) {
    return null;
  }

  return buildRequestUrl(normalizedFallback, endpoint);
}

function isTimeoutError(error: unknown): boolean {
  return (
    error instanceof DOMException && error.name === 'AbortError'
  );
}

function toNetworkErrorMessage(error: unknown, timeoutMs: number): string {
  if (isTimeoutError(error)) {
    const seconds = Math.round(timeoutMs / 1000);
    // For long-running write actions (PlanMode apply / next meal write), we want an
    // "explainable" timeout that suggests idempotent retry to fetch the result.
    if (seconds >= 60) {
      return (
        `请求超时（>${seconds}秒）。后端可能仍在后台写入中，你可以点击“重试获取结果”。`
      );
    }
    return `请求超时（>${seconds}秒），请稍后重试。`;
  }
  if (error instanceof TypeError) {
    return '网络连接异常，请检查网络后重试。';
  }
  return String(error instanceof Error ? error.message : 'Unknown network error');
}

async function fetchWithTimeout(
  url: string,
  init?: RequestInit,
  timeoutMs: number = API_TIMEOUT_MS,
): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, {
      ...init,
      signal: controller.signal,
    });
  } finally {
    window.clearTimeout(timeoutId);
  }
}

async function requestWithFallback(
  endpoint: string,
  init?: RequestInit,
  options?: RequestOptions,
): Promise<Response> {
  const timeoutMs = options?.timeoutMs ?? API_TIMEOUT_MS;
  const preferFallback = Boolean(options?.preferFallback);

  const baseUrl = buildRequestUrl(API_BASE, endpoint);
  const fallbackBaseUrl = getFallbackUrl(endpoint);

  const primaryUrl = preferFallback && fallbackBaseUrl ? fallbackBaseUrl : baseUrl;
  const fallbackUrl = preferFallback && fallbackBaseUrl ? baseUrl : fallbackBaseUrl;

  try {
    const primaryResponse = await fetchWithTimeout(primaryUrl, init, timeoutMs);
    if (!fallbackUrl || !RETRYABLE_STATUS_CODES.has(primaryResponse.status)) {
      return primaryResponse;
    }

    console.warn(
      `[api] primary request returned ${primaryResponse.status}, retrying via fallback: ${fallbackUrl}`,
    );
    return await fetchWithTimeout(fallbackUrl, init, timeoutMs);
  } catch (error) {
    if (!fallbackUrl || (!isTimeoutError(error) && !(error instanceof TypeError))) {
      throw new Error(toNetworkErrorMessage(error, timeoutMs));
    }

    console.warn(
      `[api] primary request failed, retrying via fallback: ${fallbackUrl}`,
      error,
    );
    try {
      return await fetchWithTimeout(fallbackUrl, init, timeoutMs);
    } catch (fallbackError) {
      throw new Error(toNetworkErrorMessage(fallbackError, timeoutMs));
    }
  }
}

/**
 * Create authorization headers
 */
export function createAuthHeaders(token?: string): HeadersInit | undefined {
  return token ? { Authorization: `Bearer ${token}` } : undefined;
}

/**
 * Create headers with content-type and optional auth
 */
export function createJsonHeaders(token?: string): HeadersInit {
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

/**
 * Custom error for 401 Unauthorized responses
 */
export class UnauthorizedError extends Error {
  constructor(message: string = 'Unauthorized') {
    super(message);
    this.name = 'UnauthorizedError';
  }
}

/**
 * Parse typical FastAPI error responses (Pydantic validation errors or HTTPException)
 * and return a friendly message string.
 */
export async function parseErrorResponse(response: Response): Promise<string> {
  // Handle 401 Unauthorized.
  //
  // Important: `/auth/login` can legitimately return 401 for invalid credentials.
  // In that case we must NOT treat it as "token expired" (no token yet) and we
  // want to surface the backend's `detail` message to the user instead of a
  // generic "Unauthorized".
  const responseUrl = response.url || '';
  const isAuthLoginRequest = responseUrl.includes('/auth/login');
  if (response.status === 401 && !isAuthLoginRequest) {
    localStorage.removeItem(STORAGE_KEYS.TOKEN);
    localStorage.removeItem(STORAGE_KEYS.USERNAME);
    // Dispatch custom event to notify auth context
    window.dispatchEvent(new Event('auth-unauthorized'));
    throw new UnauthorizedError();
  }

  const contentType = response.headers.get('content-type') || '';
  
  try {
    if (contentType.includes('application/json')) {
      const body = await response.json();

      // Pydantic validation errors use `detail` as an array of error objects
      if (Array.isArray(body.detail)) {
        const parts = body.detail.map((err: { loc?: string[]; msg: string; ctx?: Record<string, unknown> }) => {
          const loc = Array.isArray(err.loc) ? err.loc.filter(Boolean) : [];
          const field = loc.length ? loc[loc.length - 1] : 'field';
          const msg = typeof err.msg === 'string' ? err.msg : JSON.stringify(err.msg);
          return `${capitalize(String(field))}: ${friendlyMessageFor(msg, err.ctx)}`.trim();
        });
        const joined = parts.join('\n');
        // Deployment skew guard: older backend only supports `tags|reply` but
        // newer frontend may call `polish|card`. Convert the raw schema error
        // into a product-facing hint.
        if (joined.includes("Mode: Input should be 'tags' or 'reply'")) {
          return '后端尚未升级到支持 AI 润色/点评，请稍后刷新重试。';
        }
        return joined;
      }

      // If detail is a string, return it
      if (typeof body.detail === 'string') {
        const detail = body.detail.trim();
        // FastAPI default 404 is usually JSON: {"detail":"Not Found"}.
        // Convert it into a product-facing hint instead of showing raw "Not Found".
        if (detail === 'Not Found') {
          return (
            '接口不存在（404 Not Found）。这通常是后端尚未部署到最新版本或前后端版本未同步导致，'
            + '请刷新页面或稍后重试。'
          );
        }
        return detail;
      }

      // Fallback to message or stringified body
      if (body.message) return String(body.message);
      return JSON.stringify(body);
    }
    
    // Not JSON; return raw text
    const text = (await response.text()) || '';
    const normalized = text.trim();

    // Vercel proxy / rewrite errors sometimes return an HTML error page with a short code.
    // Surface a user-friendly message instead of dumping HTML into the UI.
    if (normalized.includes('ROUTER_EXTERNAL_TARGET_ERROR')) {
      return (
        '当前前端代理无法连接后端服务（ROUTER_EXTERNAL_TARGET_ERROR）。'
        + '这通常是后端冷启动或网络抖动导致，请稍后重试。'
      );
    }

    if (normalized.toLowerCase().includes('<!doctype') || normalized.toLowerCase().includes('<html')) {
      console.warn('[api] non-json error response (html):', normalized.slice(0, 500));
      return '请求失败（服务返回了错误页面），请稍后重试。';
    }

    // Plain text error
    if (normalized === 'Not Found') {
      return (
        '接口不存在（404 Not Found）。这通常是后端尚未部署到最新版本或代理路由未生效导致，'
        + '请刷新页面或稍后重试。'
      );
    }
    return normalized || `HTTP error! status: ${response.status}`;
  } catch (e) {
    return String(e instanceof Error ? e.message : 'Unknown error');
  }
}

async function parseSuccessResponse<T>(response: Response): Promise<T> {
  if (response.status === 204 || response.status === 205) {
    return undefined as T;
  }

  const contentLength = response.headers.get('content-length');
  if (contentLength === '0') {
    return undefined as T;
  }

  const text = await response.text();
  if (!text.trim()) {
    return undefined as T;
  }

  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('json')) {
    return JSON.parse(text) as T;
  }

  return text as T;
}

/**
 * Convert error messages to user-friendly format
 */
function friendlyMessageFor(msg: string, ctx?: Record<string, unknown>): string {
  if (msg.includes('at least') && ctx && ctx.min_length) {
    return `Must be at least ${ctx.min_length} characters`;
  }
  if (msg.includes('field required') || msg === 'value_error.missing') {
    return 'This field is required';
  }
  return msg;
}

/**
 * Make a GET request
 */
export async function apiGet<T>(
  endpoint: string,
  token?: string,
  options?: RequestOptions,
): Promise<T> {
  const response = await requestWithFallback(
    endpoint,
    { headers: createAuthHeaders(token) },
    options,
  );

  if (!response.ok) {
    const msg = await parseErrorResponse(response);
    throw new Error(msg || `HTTP error! status: ${response.status}`);
  }

  return parseSuccessResponse<T>(response);
}

/**
 * Make a POST request
 */
export async function apiPost<T, D = unknown>(
  endpoint: string,
  data: D,
  token?: string,
  options?: RequestOptions,
): Promise<T> {
  const response = await requestWithFallback(
    endpoint,
    {
      method: 'POST',
      headers: createJsonHeaders(token),
      body: JSON.stringify(data),
    },
    options,
  );

  if (!response.ok) {
    const msg = await parseErrorResponse(response);
    throw new Error(msg || `HTTP error! status: ${response.status}`);
  }

  return parseSuccessResponse<T>(response);
}

/**
 * Make a PUT request
 */
export async function apiPut<T, D = unknown>(
  endpoint: string,
  data: D,
  token?: string,
  options?: RequestOptions,
): Promise<T> {
  const response = await requestWithFallback(
    endpoint,
    {
      method: 'PUT',
      headers: createJsonHeaders(token),
      body: JSON.stringify(data),
    },
    options,
  );

  if (!response.ok) {
    const msg = await parseErrorResponse(response);
    throw new Error(msg || `HTTP error! status: ${response.status}`);
  }

  return parseSuccessResponse<T>(response);
}

/**
 * Make a DELETE request
 */
export async function apiDelete<T>(endpoint: string, token?: string): Promise<T> {
  const response = await requestWithFallback(
    endpoint,
    {
      method: 'DELETE',
      headers: createAuthHeaders(token),
    },
  );

  if (!response.ok) {
    const msg = await parseErrorResponse(response);
    throw new Error(msg || `HTTP error! status: ${response.status}`);
  }

  return parseSuccessResponse<T>(response);
}
