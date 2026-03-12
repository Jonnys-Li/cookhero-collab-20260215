import { useCallback, useEffect, useMemo, useState } from 'react';
import { ArrowLeft, Heart, Loader2, RefreshCcw, Send, Sparkles } from 'lucide-react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { useAuth } from '../../contexts';
import {
  addCommunityComment,
  getCommunityPostDetail,
  suggestCommunityReply,
  toggleCommunityReaction,
} from '../../services/api/community';
import type { CommunityComment, CommunityPost } from '../../types/community';

function formatTime(ts?: string | null): string {
  if (!ts) return '';
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleString();
}

function renderSnapshot(snapshot?: Record<string, unknown> | null) {
  if (!snapshot || typeof snapshot !== 'object') return null;
  const totalCalories = snapshot.total_calories as number | undefined;
  const totalProtein = snapshot.total_protein as number | undefined;
  const totalFat = snapshot.total_fat as number | undefined;
  const totalCarbs = snapshot.total_carbs as number | undefined;
  const avgDaily = snapshot.avg_daily_calories as number | undefined;
  const weekStart = snapshot.week_start_date as string | undefined;
  const weekEnd = snapshot.week_end_date as string | undefined;

  const hasAny =
    totalCalories != null ||
    totalProtein != null ||
    totalFat != null ||
    totalCarbs != null ||
    avgDaily != null;

  if (!hasAny) return null;

  return (
    <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-gray-50/70 dark:bg-gray-900/40 p-4">
      <div className="flex items-center justify-between mb-2">
        <div className="text-xs font-medium text-gray-600 dark:text-gray-300">附带周摘要</div>
        {weekStart && weekEnd && (
          <div className="text-xs text-gray-400">{weekStart} - {weekEnd}</div>
        )}
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 text-sm">
        <div className="rounded-xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 p-3">
          <div className="text-xs text-gray-500 dark:text-gray-400">总热量</div>
          <div className="font-semibold text-gray-900 dark:text-gray-100">{String(totalCalories ?? '-')}</div>
        </div>
        <div className="rounded-xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 p-3">
          <div className="text-xs text-gray-500 dark:text-gray-400">蛋白</div>
          <div className="font-semibold text-gray-900 dark:text-gray-100">{String(totalProtein ?? '-')}</div>
        </div>
        <div className="rounded-xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 p-3">
          <div className="text-xs text-gray-500 dark:text-gray-400">脂肪</div>
          <div className="font-semibold text-gray-900 dark:text-gray-100">{String(totalFat ?? '-')}</div>
        </div>
        <div className="rounded-xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 p-3">
          <div className="text-xs text-gray-500 dark:text-gray-400">碳水</div>
          <div className="font-semibold text-gray-900 dark:text-gray-100">{String(totalCarbs ?? '-')}</div>
        </div>
        <div className="rounded-xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 p-3">
          <div className="text-xs text-gray-500 dark:text-gray-400">日均</div>
          <div className="font-semibold text-gray-900 dark:text-gray-100">{String(avgDaily ?? '-')}</div>
        </div>
      </div>
    </div>
  );
}

export default function CommunityPostDetailPage() {
  const { token } = useAuth();
  const { id } = useParams<{ id: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const isAgentMode = location.pathname.startsWith('/agent');
  const basePath = isAgentMode ? '/agent/community' : '/community';

  const [post, setPost] = useState<CommunityPost | null>(null);
  const [comments, setComments] = useState<CommunityComment[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [commentText, setCommentText] = useState('');
  const [commentAnon, setCommentAnon] = useState(true);
  const [isCommenting, setIsCommenting] = useState(false);
  const [isGeneratingReply, setIsGeneratingReply] = useState(false);

  const postId = id || '';
  const canSendComment = useMemo(() => commentText.trim().length > 0 && !isCommenting, [commentText, isCommenting]);

  const fetchDetail = useCallback(async () => {
    if (!token || !postId) return;
    setIsLoading(true);
    setError(null);
    try {
      const res = await getCommunityPostDetail(token, postId);
      setPost(res.post);
      setComments(res.comments || []);
    } catch (err) {
      const msg = err instanceof Error ? err.message : '加载帖子失败';
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  }, [token, postId]);

  useEffect(() => {
    fetchDetail();
  }, [fetchDetail]);

  const handleToggleLike = async () => {
    if (!token || !postId || !post) return;
    setError(null);
    try {
      const res = await toggleCommunityReaction(token, postId);
      setPost(prev => prev ? { ...prev, liked_by_me: res.liked, like_count: res.like_count } : prev);
    } catch (err) {
      const msg = err instanceof Error ? err.message : '点赞失败';
      setError(msg);
    }
  };

  const handleGenerateReply = async () => {
    if (!token || !postId) return;
    setIsGeneratingReply(true);
    setError(null);
    try {
      const reply = await suggestCommunityReply(token, postId);
      if (!reply) {
        setError('AI 暂时没有生成合适回复, 你可以手动写一句支持的话');
        return;
      }
      setCommentText(reply);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'AI 生成回复失败';
      setError(msg);
    } finally {
      setIsGeneratingReply(false);
    }
  };

  const handleSendComment = async () => {
    if (!token || !postId || !canSendComment) return;
    setIsCommenting(true);
    setError(null);
    try {
      const res = await addCommunityComment(token, postId, {
        content: commentText.trim(),
        is_anonymous: commentAnon,
      });
      const comment = res as unknown as CommunityComment;
      setComments(prev => [...prev, comment]);
      setPost(prev => prev ? { ...prev, comment_count: (prev.comment_count || 0) + 1 } : prev);
      setCommentText('');
    } catch (err) {
      const msg = err instanceof Error ? err.message : '发表评论失败';
      setError(msg);
    } finally {
      setIsCommenting(false);
    }
  };

  if (!token) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-sm text-gray-500 dark:text-gray-400">请先登录后查看帖子</div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-3xl mx-auto px-4 py-6">
        <div className="flex items-center justify-between mb-4">
          <button
            onClick={() => navigate(basePath)}
            className="inline-flex items-center gap-2 px-3 py-2 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800"
          >
            <ArrowLeft className="w-4 h-4" />
            返回广场
          </button>

          <button
            onClick={fetchDetail}
            disabled={isLoading}
            className="inline-flex items-center gap-2 px-3 py-2 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-50"
          >
            {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCcw className="w-4 h-4" />}
            刷新
          </button>
        </div>

        {error && (
          <div className="mb-4 rounded-xl border border-red-200 bg-red-50 text-red-700 dark:border-red-900/60 dark:bg-red-900/20 dark:text-red-200 px-4 py-3 text-sm">
            {error}
          </div>
        )}

        {isLoading && !post ? (
          <div className="flex items-center justify-center py-12 text-gray-400">
            <Loader2 className="w-5 h-5 animate-spin mr-2" />
            加载中...
          </div>
        ) : !post ? (
          <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-white/70 dark:bg-gray-900/40 p-8 text-center text-gray-500 dark:text-gray-400">
            帖子不存在或已删除
          </div>
        ) : (
          <div className="space-y-4">
            <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-white/90 dark:bg-gray-900/60 shadow-sm">
              <div className="p-5">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">
                      {post.author_display_name || '匿名用户'}
                    </div>
                    <div className="text-xs text-gray-400 mt-1">{formatTime(post.created_at)}</div>
                  </div>

                  <button
                    onClick={handleToggleLike}
                    className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-xs transition-colors ${
                      post.liked_by_me
                        ? 'border-rose-300 bg-rose-50 text-rose-700 dark:border-rose-800 dark:bg-rose-900/20 dark:text-rose-200'
                        : 'border-gray-200 bg-white text-gray-600 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300 dark:hover:bg-gray-800'
                    }`}
                  >
                    <Heart className={`w-3.5 h-3.5 ${post.liked_by_me ? 'fill-current' : ''}`} />
                    {post.like_count}
                  </button>
                </div>

                <div className="mt-4 text-sm text-gray-800 dark:text-gray-200 leading-relaxed whitespace-pre-wrap">
                  {post.content}
                </div>

                {post.tags && post.tags.length > 0 && (
                  <div className="mt-4 flex flex-wrap gap-2">
                    {post.tags.slice(0, 5).map(tag => (
                      <span
                        key={tag}
                        className="text-xs px-2 py-0.5 rounded-full bg-orange-50 dark:bg-orange-900/20 text-orange-700 dark:text-orange-200 border border-orange-200/60 dark:border-orange-800/60"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                )}

                {post.image_urls && post.image_urls.length > 0 && (
                  <div className="mt-5 grid grid-cols-2 sm:grid-cols-3 gap-3">
                    {post.image_urls.slice(0, 4).map((url, idx) => (
                      <a key={idx} href={url} target="_blank" rel="noreferrer" className="block">
                        <img
                          src={url}
                          alt={`post-img-${idx}`}
                          className="w-full h-32 object-cover rounded-2xl border border-gray-200 dark:border-gray-800 hover:opacity-95 transition-opacity"
                          loading="lazy"
                        />
                      </a>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {renderSnapshot(post.nutrition_snapshot as Record<string, unknown> | null | undefined)}

            <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-white/90 dark:bg-gray-900/60 shadow-sm">
              <div className="px-5 py-4 border-b border-gray-100 dark:border-gray-800">
                <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                  评论 ({post.comment_count})
                </div>
              </div>
              <div className="p-5 space-y-4">
                {comments.length === 0 ? (
                  <div className="text-sm text-gray-500 dark:text-gray-400">
                    还没有评论。写一句温柔的话, 可能会成为别人今天的支点。
                  </div>
                ) : (
                  <div className="space-y-3">
                    {comments.map((c) => (
                      <div key={c.id} className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">
                              {c.author_display_name || '匿名用户'}
                            </div>
                            <div className="text-xs text-gray-400 mt-1">{formatTime(c.created_at)}</div>
                          </div>
                        </div>
                        <div className="mt-2 text-sm text-gray-800 dark:text-gray-200 leading-relaxed whitespace-pre-wrap">
                          {c.content}
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                <div className="pt-2 border-t border-gray-100 dark:border-gray-800">
                  <div className="flex items-center justify-between mb-2">
                    <label className="flex items-center gap-2 select-none text-sm text-gray-700 dark:text-gray-200">
                      <input
                        type="checkbox"
                        checked={commentAnon}
                        onChange={(e) => setCommentAnon(e.target.checked)}
                        className="rounded border-gray-300 dark:border-gray-700"
                      />
                      匿名评论
                    </label>
                    <button
                      onClick={handleGenerateReply}
                      disabled={isGeneratingReply}
                      className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full border border-orange-200 dark:border-orange-800 bg-orange-50 dark:bg-orange-900/20 text-orange-700 dark:text-orange-300 hover:bg-orange-100/60 dark:hover:bg-orange-900/30 transition-colors disabled:opacity-50"
                    >
                      {isGeneratingReply ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      ) : (
                        <Sparkles className="w-3.5 h-3.5" />
                      )}
                      AI 帮我回复
                    </button>
                  </div>

                  <textarea
                    value={commentText}
                    onChange={(e) => setCommentText(e.target.value)}
                    rows={3}
                    placeholder="写一句支持的话..."
                    className="w-full rounded-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-4 py-3 text-sm leading-relaxed focus:outline-none focus:ring-2 focus:ring-orange-200 dark:focus:ring-orange-900/30"
                  />
                  <div className="mt-2 flex justify-end">
                    <button
                      onClick={handleSendComment}
                      disabled={!canSendComment}
                      className="px-4 py-2 rounded-xl bg-orange-500 text-white text-sm font-medium hover:bg-orange-600 disabled:opacity-50 inline-flex items-center gap-2"
                    >
                      {isCommenting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                      发布评论
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

