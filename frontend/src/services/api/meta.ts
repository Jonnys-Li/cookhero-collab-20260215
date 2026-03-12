/**
 * Meta API services
 *
 * Used for capability probing to avoid frontend/backend deployment skew.
 */

import { apiGet } from './client';
import type { CapabilitiesResponse } from '../../types/api';

let cachedCapabilities: CapabilitiesResponse | null = null;
let inflight: Promise<CapabilitiesResponse> | null = null;

export async function getCapabilities(
  token: string,
  opts?: { force?: boolean }
): Promise<CapabilitiesResponse> {
  const force = Boolean(opts?.force);
  if (!force && cachedCapabilities) return cachedCapabilities;
  if (!force && inflight) return inflight;

  inflight = apiGet<CapabilitiesResponse>('/meta/capabilities', token)
    .then((res) => {
      cachedCapabilities = res || {};
      return cachedCapabilities;
    })
    .catch((err) => {
      // Cache a "negative" result so callers can degrade gracefully without
      // repeatedly hammering the endpoint.
      cachedCapabilities = {};
      console.warn('[meta] capabilities probe failed, degrading gracefully:', err);
      return cachedCapabilities;
    })
    .finally(() => {
      inflight = null;
    });

  return inflight;
}
