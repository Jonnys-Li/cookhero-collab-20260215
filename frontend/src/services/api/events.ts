/**
 * Product events (analytics) API.
 *
 * Contract (backend-owned):
 * - POST /api/v1/events (auth required)
 * - body: { event_name: string; props?: Record<string, unknown> }
 *
 * NOTE: Event reporting must never break user flows. This module intentionally
 * swallows network errors and logs to console.
 */

import { apiPost } from './client';

export const EVENTS_ENDPOINT = '/events';

export type ProductEventPayload = {
  event_name: string;
  props?: Record<string, unknown>;
};

export async function trackEvent(
  token: string,
  eventName: string,
  props?: Record<string, unknown>
): Promise<void> {
  if (!token) return;

  try {
    await apiPost<Record<string, unknown>, ProductEventPayload>(
      EVENTS_ENDPOINT,
      { event_name: eventName, props },
      token,
      { timeoutMs: 8000 }
    );
  } catch (err) {
    console.warn('[events] report failed:', err);
  }
}
