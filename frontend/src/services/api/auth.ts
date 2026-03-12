/**
 * Authentication API services
 */

import { apiPost } from './client';
import type { Credentials, AuthResponse } from '../../types';

const AUTH_TIMEOUT_MS = 20000;

/**
 * User login
 */
export async function login(credentials: Credentials): Promise<AuthResponse> {
  return apiPost<AuthResponse>('/auth/login', credentials, undefined, {
    timeoutMs: AUTH_TIMEOUT_MS,
    preferFallback: true,
  });
}

/**
 * User registration
 */
export async function register(credentials: Credentials): Promise<AuthResponse> {
  return apiPost<AuthResponse>('/auth/register', credentials, undefined, {
    timeoutMs: AUTH_TIMEOUT_MS,
    preferFallback: true,
  });
}

/**
 * Refresh authentication token
 */
export async function refreshToken(token: string): Promise<AuthResponse> {
  return apiPost<AuthResponse>('/auth/refresh', {}, token, {
    timeoutMs: AUTH_TIMEOUT_MS,
    preferFallback: true,
  });
}
