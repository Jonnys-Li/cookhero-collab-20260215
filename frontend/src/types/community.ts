export type CommunityMood = 'happy' | 'neutral' | 'anxious' | 'guilty' | 'tired';

export type CommunityPostType = 'check_in';

export interface CommunityImageData {
  data: string;
  mime_type: string;
}

export interface CommunityPost {
  id: string;
  user_id: string;
  author_display_name: string;
  is_anonymous: boolean;
  post_type: CommunityPostType;
  mood?: CommunityMood | string | null;
  content: string;
  tags: string[];
  image_urls: string[];
  nutrition_snapshot?: Record<string, unknown> | null;
  like_count: number;
  comment_count: number;
  liked_by_me: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface CommunityComment {
  id: string;
  post_id: string;
  user_id: string;
  author_display_name: string;
  is_anonymous: boolean;
  content: string;
  created_at?: string | null;
}

export interface CommunityFeedResponse {
  posts: CommunityPost[];
  total: number;
}

export interface CommunityPostDetailResponse {
  post: CommunityPost;
  comments: CommunityComment[];
}

export interface CreateCommunityPostRequest {
  is_anonymous?: boolean;
  mood?: CommunityMood | string | null;
  content: string;
  tags?: string[];
  images?: CommunityImageData[];
  nutrition_snapshot?: Record<string, unknown> | null;
}

export interface CreateCommunityCommentRequest {
  content: string;
  is_anonymous?: boolean;
}

export interface ToggleCommunityReactionResponse {
  liked: boolean;
  like_count: number;
}

export type CommunityAISuggestMode = 'tags' | 'reply' | 'card' | 'polish';

export interface CommunityAISuggestRequest {
  mode: CommunityAISuggestMode;
  content?: string;
  post_id?: string;
}

export interface CommunityAISuggestTagsResponse {
  tags: string[];
}

export interface CommunityAISuggestReplyResponse {
  reply: string;
}

export interface CommunityAISuggestCardResponse {
  card: string;
}

export interface CommunityAISuggestPolishResponse {
  polished: string;
}
