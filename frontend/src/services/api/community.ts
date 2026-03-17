/**
 * Community API service (Check-in mutual help square)
 */

import { apiGet, apiPost, apiDelete } from './client';
import type {
  CommunityFeedResponse,
  CommunityPostDetailResponse,
  CreateCommunityPostRequest,
  CreateCommunityCommentRequest,
  ToggleCommunityReactionResponse,
  CommunityAISuggestTagsResponse,
  CommunityAISuggestReplyResponse,
  CommunityAISuggestCardResponse,
  CommunityAISuggestPolishResponse,
  CommunityAISuggestRequest,
} from '../../types/community';

const COMMUNITY_BASE = '/community';

export async function getCommunityFeed(
  token: string,
  params?: {
    limit?: number;
    offset?: number;
    tag?: string;
    mood?: string;
    sort?: 'latest' | 'need_support' | 'hot';
  }
): Promise<CommunityFeedResponse> {
  const query = new URLSearchParams();
  query.set('limit', String(params?.limit ?? 20));
  query.set('offset', String(params?.offset ?? 0));
  if (params?.tag) query.set('tag', params.tag);
  if (params?.mood) query.set('mood', params.mood);
  if (params?.sort) query.set('sort', params.sort);
  return apiGet<CommunityFeedResponse>(`${COMMUNITY_BASE}/feed?${query.toString()}`, token);
}

export async function createCommunityPost(
  token: string,
  data: CreateCommunityPostRequest
): Promise<Record<string, unknown>> {
  return apiPost<Record<string, unknown>, CreateCommunityPostRequest>(
    `${COMMUNITY_BASE}/posts`,
    data,
    token,
    {
      // Write-like action: allow cold start and image upload latency.
      //
      // Note: preferFallback=true would call Render cross-origin first, which
      // triggers CORS preflight. We keep the same-origin Vercel proxy as the
      // primary path to avoid CORS surprises, and rely on the client's
      // automatic fallback on timeout/5xx/network errors.
      timeoutMs: 60000,
    }
  );
}

export async function getCommunityPostDetail(
  token: string,
  postId: string,
  params?: { comment_limit?: number; comment_offset?: number }
): Promise<CommunityPostDetailResponse> {
  const query = new URLSearchParams();
  query.set('comment_limit', String(params?.comment_limit ?? 50));
  query.set('comment_offset', String(params?.comment_offset ?? 0));
  return apiGet<CommunityPostDetailResponse>(
    `${COMMUNITY_BASE}/posts/${postId}?${query.toString()}`,
    token
  );
}

export async function addCommunityComment(
  token: string,
  postId: string,
  data: CreateCommunityCommentRequest
): Promise<Record<string, unknown>> {
  return apiPost<Record<string, unknown>, CreateCommunityCommentRequest>(
    `${COMMUNITY_BASE}/posts/${postId}/comments`,
    data,
    token,
    {
      timeoutMs: 60000,
    }
  );
}

export async function toggleCommunityReaction(
  token: string,
  postId: string
): Promise<ToggleCommunityReactionResponse> {
  return apiPost<ToggleCommunityReactionResponse, Record<string, never>>(
    `${COMMUNITY_BASE}/posts/${postId}/reactions/toggle`,
    {},
    token,
    {
      timeoutMs: 60000,
    }
  );
}

export async function deleteCommunityPost(
  token: string,
  postId: string
): Promise<{ message: string }> {
  return apiDelete<{ message: string }>(`${COMMUNITY_BASE}/posts/${postId}`, token);
}

export async function deleteCommunityComment(
  token: string,
  commentId: string
): Promise<{ message: string }> {
  return apiDelete<{ message: string }>(`${COMMUNITY_BASE}/comments/${commentId}`, token);
}

export async function communityAiSuggest(
  token: string,
  payload: CommunityAISuggestRequest
): Promise<
  CommunityAISuggestTagsResponse | CommunityAISuggestReplyResponse | CommunityAISuggestCardResponse
  | CommunityAISuggestPolishResponse
> {
  return apiPost<
    CommunityAISuggestTagsResponse
    | CommunityAISuggestReplyResponse
    | CommunityAISuggestCardResponse
    | CommunityAISuggestPolishResponse,
    CommunityAISuggestRequest
  >(`${COMMUNITY_BASE}/ai/suggest`, payload, token, {
    timeoutMs: 60000,
  });
}

export async function suggestCommunityTags(
  token: string,
  content: string
): Promise<string[]> {
  const result = await communityAiSuggest(token, { mode: 'tags', content });
  const tags = (result as CommunityAISuggestTagsResponse).tags;
  return Array.isArray(tags) ? tags : [];
}

export async function suggestCommunityReply(
  token: string,
  postId: string
): Promise<string> {
  const result = await communityAiSuggest(token, { mode: 'reply', post_id: postId });
  const reply = (result as CommunityAISuggestReplyResponse).reply;
  return typeof reply === 'string' ? reply : '';
}

export async function suggestCommunityCard(
  token: string,
  postId: string
): Promise<string> {
  const result = await communityAiSuggest(token, { mode: 'card', post_id: postId });
  const card = (result as CommunityAISuggestCardResponse).card;
  return typeof card === 'string' ? card : '';
}

export async function polishCommunityPost(
  token: string,
  content: string
): Promise<string> {
  const result = await communityAiSuggest(token, { mode: 'polish', content });
  const polished = (result as CommunityAISuggestPolishResponse).polished;
  return typeof polished === 'string' ? polished : '';
}
