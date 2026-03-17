import { useCallback, useEffect, useMemo, useState } from 'react';
import { Heart, Loader2, MessageCircle, Plus, RefreshCcw, Sparkles, Users } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../../contexts';
import { getCommunityFeed, suggestCommunityCard, toggleCommunityReaction } from '../../services/api/community';
import { getCapabilities } from '../../services/api/meta';
import type { CommunityPost } from '../../types/community';
import { CreatePostModal } from './CreatePostModal';

const TAG_OPTIONS: string[] = [
  '',
  '减脂',
  '增肌',
  '控糖',
  '外食',
  '高蛋白',
  '低碳',
  '暴食后自责',
  '焦虑',
  '想放弃',
  '求建议',
  '坚持打卡',
];

const MOOD_OPTIONS: Array<{ value: string; label: string }> = [
  { value: '', label: '全部情绪' },
  { value: 'happy', label: '开心' },
  { value: 'neutral', label: '平稳' },
  { value: 'anxious', label: '焦虑' },
  { value: 'guilty', label: '内疚' },
  { value: 'tired', label: '疲惫' },
];

function formatTime(ts?: string | null): string {
  if (!ts) return '';
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleString();
}

function daysAgo(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString();
}

const DEMO_COMMUNITY_POSTS: CommunityPost[] = [
  {
    id: 'demo-1',
    user_id: 'demo',
    author_display_name: '匿名小厨0421',
    is_anonymous: true,
    post_type: 'check_in',
    mood: 'neutral',
    content:
      '今天按计划吃了三餐，外食也尽量选了清淡少油的搭配。虽然没做到完美，但能坚持记录就很不错了，明天继续。',
    tags: ['坚持打卡', '外食'],
    image_urls: [],
    nutrition_snapshot: null,
    like_count: 12,
    comment_count: 3,
    liked_by_me: false,
    created_at: daysAgo(0),
    updated_at: daysAgo(0),
  },
  {
    id: 'demo-2',
    user_id: 'demo',
    author_display_name: '匿名小厨8190',
    is_anonymous: true,
    post_type: 'check_in',
    mood: 'anxious',
    content:
      '今天工作压力有点大，晚饭想吃点甜的缓解情绪。有没有更容易坚持的替代方案？我不想靠自责来逼自己。',
    tags: ['焦虑', '求建议'],
    image_urls: [],
    nutrition_snapshot: null,
    like_count: 8,
    comment_count: 5,
    liked_by_me: false,
    created_at: daysAgo(1),
    updated_at: daysAgo(1),
  },
  {
    id: 'demo-3',
    user_id: 'demo',
    author_display_name: '匿名小厨1266',
    is_anonymous: true,
    post_type: 'check_in',
    mood: 'guilty',
    content:
      '晚上没忍住吃多了，心里有点内疚。现在更想做的是把节奏找回来：先把下一顿安排得简单一点，不再和自己较劲。',
    tags: ['暴食后自责', '想放弃'],
    image_urls: [],
    nutrition_snapshot: null,
    like_count: 15,
    comment_count: 7,
    liked_by_me: false,
    created_at: daysAgo(2),
    updated_at: daysAgo(2),
  },
  {
    id: 'demo-4',
    user_id: 'demo',
    author_display_name: '匿名小厨5502',
    is_anonymous: true,
    post_type: 'check_in',
    mood: 'happy',
    content:
      '今天训练后补了高蛋白餐，感觉精神状态挺好。打卡一下，也想听听大家都怎么安排训练日的饮食。',
    tags: ['高蛋白', '增肌'],
    image_urls: [],
    nutrition_snapshot: {
      week_start_date: '2026-03-02',
      week_end_date: '2026-03-08',
      total_calories: 11250,
      total_protein: 680,
      total_fat: 320,
      total_carbs: 980,
      avg_daily_calories: 1607,
    },
    like_count: 20,
    comment_count: 9,
    liked_by_me: false,
    created_at: daysAgo(4),
    updated_at: daysAgo(4),
  },
];

export default function CommunityFeedPage() {
  const { token } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const isAgentMode = location.pathname.startsWith('/agent');
  const basePath = isAgentMode ? '/agent/community' : '/community';

  const [posts, setPosts] = useState<CommunityPost[]>([]);
  const [total, setTotal] = useState(0);
  const [selectedSort, setSelectedSort] = useState<'latest' | 'need_support'>('latest');
  const [selectedTag, setSelectedTag] = useState('');
  const [selectedMood, setSelectedMood] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

  const [capabilitiesLoading, setCapabilitiesLoading] = useState(false);
  const [communityAiModes, setCommunityAiModes] = useState<string[]>([]);

  const [aiCards, setAiCards] = useState<
    Record<
      string,
      {
        open: boolean;
        loading: boolean;
        text: string;
        error: string | null;
      }
    >
  >({});

  const canLoadMore = useMemo(() => posts.length < total, [posts.length, total]);
  const canUseAICard = useMemo(
    () => communityAiModes.includes('card'),
    [communityAiModes]
  );

  const demoPosts = useMemo(() => {
    return DEMO_COMMUNITY_POSTS.filter((p) => {
      if (selectedMood && String(p.mood || '') !== selectedMood) return false;
      if (selectedTag && !(p.tags || []).includes(selectedTag)) return false;
      return true;
    });
  }, [selectedMood, selectedTag]);

  const fetchFeed = useCallback(async (opts?: { append?: boolean }) => {
    if (!token) return;
    const append = Boolean(opts?.append);
    if (append) {
      setIsLoadingMore(true);
    } else {
      setIsLoading(true);
    }
    setError(null);
    try {
      const res = await getCommunityFeed(token, {
        limit: 20,
        offset: append ? posts.length : 0,
        sort: selectedSort,
        tag: selectedTag || undefined,
        mood: selectedMood || undefined,
      });
      setTotal(res.total || 0);
      setPosts(prev => (append ? [...prev, ...res.posts] : res.posts));
    } catch (err) {
      const msg = err instanceof Error ? err.message : '加载社区失败，请稍后重试';
      setError(msg);
    } finally {
      setIsLoading(false);
      setIsLoadingMore(false);
    }
  }, [token, posts.length, selectedSort, selectedTag, selectedMood]);

  useEffect(() => {
    setPosts([]);
    setTotal(0);
    if (!token) return;
    fetchFeed({ append: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, selectedSort, selectedTag, selectedMood]);

  useEffect(() => {
    if (!token) {
      setCommunityAiModes([]);
      return;
    }

    let cancelled = false;
    setCapabilitiesLoading(true);
    getCapabilities(token)
      .then((res) => {
        if (cancelled) return;
        const modes = Array.isArray(res?.community_ai_modes) ? res.community_ai_modes : [];
        setCommunityAiModes(modes.map(String));
      })
      .finally(() => {
        if (!cancelled) setCapabilitiesLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [token]);

  const handleOpenDetail = (postId: string) => {
    navigate(`${basePath}/${postId}`);
  };

  const handleToggleLike = async (postId: string) => {
    if (!token) return;
    try {
      const res = await toggleCommunityReaction(token, postId);
      setPosts(prev =>
        prev.map(p =>
          p.id === postId
            ? { ...p, liked_by_me: res.liked, like_count: res.like_count }
            : p
        )
      );
    } catch (err) {
      const msg = err instanceof Error ? err.message : '点赞失败，请稍后重试';
      setError(msg);
    }
  };

  const handleToggleAICard = useCallback(async (postId: string) => {
    if (!token) return;
    if (!canUseAICard) {
      setError('后端升级中，暂不支持 AI 共情点评，请稍后刷新重试。');
      return;
    }

    let shouldGenerate = false;
    setAiCards(prev => {
      const current = prev[postId];
      if (current?.open) {
        return { ...prev, [postId]: { ...current, open: false } };
      }
      const next = {
        open: true,
        loading: Boolean(current?.loading),
        text: current?.text || '',
        error: null,
      };
      if (!next.text && !next.loading) {
        shouldGenerate = true;
      }
      return { ...prev, [postId]: next };
    });

    if (!shouldGenerate) return;

    setAiCards(prev => ({
      ...prev,
      [postId]: {
        ...(prev[postId] || { open: true, text: '' }),
        open: true,
        loading: true,
        error: null,
      },
    }));

    try {
      const card = await suggestCommunityCard(token, postId);
      if (!card) {
        throw new Error('AI 暂时没有给出有效点评，请稍后重试');
      }
      setAiCards(prev => ({
        ...prev,
        [postId]: {
          ...(prev[postId] || { open: true }),
          open: true,
          loading: false,
          text: card,
          error: null,
        },
      }));
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'AI 共情点评生成失败，请稍后重试';
      setAiCards(prev => ({
        ...prev,
        [postId]: {
          ...(prev[postId] || { open: true, text: '' }),
          open: true,
          loading: false,
          text: '',
          error: msg,
        },
      }));
    }
  }, [token, canUseAICard]);

  const handleRegenerateAICard = useCallback(async (postId: string) => {
    if (!token) return;
    if (!canUseAICard) {
      setError('后端升级中，暂不支持 AI 共情点评，请稍后刷新重试。');
      return;
    }
    setAiCards(prev => ({
      ...prev,
      [postId]: {
        ...(prev[postId] || { open: true, text: '' }),
        open: true,
        loading: true,
        error: null,
      },
    }));

    try {
      const card = await suggestCommunityCard(token, postId);
      if (!card) {
        throw new Error('AI 暂时没有给出有效点评，请稍后重试');
      }
      setAiCards(prev => ({
        ...prev,
        [postId]: {
          ...(prev[postId] || { open: true }),
          open: true,
          loading: false,
          text: card,
          error: null,
        },
      }));
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'AI 共情点评生成失败，请稍后重试';
      setAiCards(prev => ({
        ...prev,
        [postId]: {
          ...(prev[postId] || { open: true, text: '' }),
          open: true,
          loading: false,
          text: '',
          error: msg,
        },
      }));
    }
  }, [token, canUseAICard]);

  if (!token) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-sm text-gray-500 dark:text-gray-400">请先登录后查看社区</div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-4xl mx-auto px-4 py-6">
        <div className="flex items-start justify-between gap-4 mb-5">
          <div>
            <div className="flex items-center gap-2">
              <div className="p-2 rounded-2xl bg-orange-50 dark:bg-orange-900/20 border border-orange-200 dark:border-orange-800 text-orange-600 dark:text-orange-300">
                <Users className="w-5 h-5" />
              </div>
              <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">打卡互助广场</h2>
            </div>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-2">
              记录, 共情, 纠偏。内容仅供参考, 不替代专业医疗建议。
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => fetchFeed({ append: false })}
              disabled={isLoading}
              className="px-3 py-2 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-50 inline-flex items-center gap-2"
            >
              {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCcw className="w-4 h-4" />}
              刷新
            </button>
            <button
              onClick={() => setIsModalOpen(true)}
              className="px-3 py-2 rounded-xl bg-orange-500 text-white text-sm font-medium hover:bg-orange-600 inline-flex items-center gap-2"
            >
              <Plus className="w-4 h-4" />
              发一条
            </button>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3 mb-4">
          <div className="inline-flex rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 overflow-hidden">
            <button
              type="button"
              onClick={() => setSelectedSort('latest')}
              aria-pressed={selectedSort === 'latest'}
              className={`px-3 py-2 text-sm transition-colors ${
                selectedSort === 'latest'
                  ? 'bg-orange-500 text-white'
                  : 'text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800'
              }`}
            >
              最新
            </button>
            <button
              type="button"
              onClick={() => setSelectedSort('need_support')}
              aria-pressed={selectedSort === 'need_support'}
              className={`px-3 py-2 text-sm transition-colors ${
                selectedSort === 'need_support'
                  ? 'bg-orange-500 text-white'
                  : 'text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800'
              }`}
            >
              需要支持
            </button>
          </div>

          <select
            value={selectedTag}
            onChange={(e) => setSelectedTag(e.target.value)}
            className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm text-gray-700 dark:text-gray-200"
          >
            <option value="">全部标签</option>
            {TAG_OPTIONS.filter(t => t).map(tag => (
              <option key={tag} value={tag}>{tag}</option>
            ))}
          </select>

          <select
            value={selectedMood}
            onChange={(e) => setSelectedMood(e.target.value)}
            className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm text-gray-700 dark:text-gray-200"
          >
            {MOOD_OPTIONS.map(m => (
              <option key={m.value} value={m.value}>{m.label}</option>
            ))}
          </select>

          <div className="text-xs text-gray-400">
            共 {total} 条
          </div>
        </div>

        {error && (
          <div className="mb-4 rounded-xl border border-red-200 bg-red-50 text-red-700 dark:border-red-900/60 dark:bg-red-900/20 dark:text-red-200 px-4 py-3 text-sm">
            {error}
          </div>
        )}

        {isLoading && posts.length === 0 ? (
          <div className="flex items-center justify-center py-12 text-gray-400">
            <Loader2 className="w-5 h-5 animate-spin mr-2" />
            加载中...
          </div>
        ) : posts.length > 0 ? (
          <div className="space-y-4">
            {posts.map(post => (
              <div
                key={post.id}
                className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-white/90 dark:bg-gray-900/60 shadow-sm hover:shadow-md transition-all cursor-pointer"
                onClick={() => handleOpenDetail(post.id)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleOpenDetail(post.id);
                }}
              >
                <div className="p-5">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">
                          {post.author_display_name || '匿名用户'}
                        </span>
                        {post.mood && (
                          <span className="text-xs px-2 py-0.5 rounded-full border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-gray-600 dark:text-gray-300">
                            {MOOD_OPTIONS.find(m => m.value === post.mood)?.label || String(post.mood)}
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-gray-400 mt-1">
                        {formatTime(post.created_at)}
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleToggleLike(post.id);
                        }}
                        className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-xs transition-colors ${
                          post.liked_by_me
                            ? 'border-rose-300 bg-rose-50 text-rose-700 dark:border-rose-800 dark:bg-rose-900/20 dark:text-rose-200'
                            : 'border-gray-200 bg-white text-gray-600 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300 dark:hover:bg-gray-800'
                        }`}
                      >
                        <Heart className={`w-3.5 h-3.5 ${post.liked_by_me ? 'fill-current' : ''}`} />
                        {post.like_count}
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleToggleAICard(post.id);
                        }}
                        disabled={!canUseAICard || capabilitiesLoading}
                        className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-xs transition-colors ${
                          !canUseAICard || capabilitiesLoading
                            ? 'border-gray-200 bg-white text-gray-400 opacity-60 cursor-not-allowed dark:border-gray-700 dark:bg-gray-900 dark:text-gray-500'
                            : 'border-gray-200 bg-white text-gray-600 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300 dark:hover:bg-gray-800'
                        }`}
                        title={
                          capabilitiesLoading
                            ? '正在检测后端能力...'
                            : (!canUseAICard ? '后端升级中，稍后刷新' : '点击生成共情点评小卡（不会自动消耗）')
                        }
                      >
                        {capabilitiesLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
                        AI 共情点评
                      </button>
                      <div className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 text-xs text-gray-600 dark:text-gray-300">
                        <MessageCircle className="w-3.5 h-3.5" />
                        {post.comment_count}
                      </div>
                    </div>
                  </div>

                  <div className="mt-4 text-sm text-gray-800 dark:text-gray-200 leading-relaxed">
                    {post.content.length > 180 ? `${post.content.slice(0, 180)}...` : post.content}
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

                  {aiCards[post.id]?.open && (
                    <div
                      className="mt-4 rounded-2xl border border-orange-200/70 dark:border-orange-800/50 bg-orange-50/70 dark:bg-orange-900/10 p-4"
                      onClick={(e) => e.stopPropagation()}
                      role="presentation"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className="inline-flex items-center gap-2 text-xs font-semibold text-orange-800 dark:text-orange-200">
                          <Sparkles className="w-4 h-4" />
                          AI 共情点评小卡
                        </div>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleRegenerateAICard(post.id);
                          }}
                          className="text-xs px-2.5 py-1 rounded-full border border-orange-200 dark:border-orange-800 bg-white/80 dark:bg-gray-900/30 text-orange-700 dark:text-orange-200 hover:bg-white dark:hover:bg-gray-900/50 transition-colors"
                        >
                          换一条
                        </button>
                      </div>

                      <div className="mt-3">
                        {aiCards[post.id]?.loading ? (
                          <div className="flex items-center text-sm text-orange-700 dark:text-orange-200">
                            <Loader2 className="w-4 h-4 animate-spin mr-2" />
                            正在生成点评...
                          </div>
                        ) : aiCards[post.id]?.error ? (
                          <div className="text-sm text-red-700 dark:text-red-200">
                            {aiCards[post.id]?.error}
                          </div>
                        ) : (
                          <div className="text-sm text-gray-800 dark:text-gray-100 leading-relaxed">
                            {aiCards[post.id]?.text}
                          </div>
                        )}
                      </div>

                      <div className="mt-2 text-[11px] text-gray-500 dark:text-gray-400">
                        仅供参考，不替代专业医疗建议。
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ))}

            {canLoadMore && (
              <div className="flex justify-center pt-2">
                <button
                  onClick={() => fetchFeed({ append: true })}
                  disabled={isLoadingMore}
                  className="px-4 py-2 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-50 inline-flex items-center gap-2"
                >
                  {isLoadingMore && <Loader2 className="w-4 h-4 animate-spin" />}
                  加载更多
                </button>
              </div>
            )}
          </div>
        ) : (
          <div className="space-y-4">
            <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-white/70 dark:bg-gray-900/40 p-8 text-center text-gray-500 dark:text-gray-400">
              还没有真实打卡内容。发一条, 给别人一点温暖, 也给自己一点力量。
            </div>

            <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-white/80 dark:bg-gray-900/50 p-5">
              <div className="flex items-center justify-between gap-3">
                <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                  示例数据（仅用于演示，不会写入）
                </div>
                <div className="text-xs text-gray-400">
                  {demoPosts.length} 条
                </div>
              </div>
              <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                这些卡片用于展示“打卡互助 + 共情干预”的交互形态，实际使用以真实数据为准。
              </div>

              {demoPosts.length === 0 ? (
                <div className="mt-4 text-sm text-gray-500 dark:text-gray-400">
                  当前筛选条件下暂无示例数据。
                </div>
              ) : (
                <div className="mt-4 space-y-4">
                  {demoPosts.map((post) => (
                    <div
                      key={post.id}
                      className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-white/90 dark:bg-gray-900/60 shadow-sm"
                      role="group"
                    >
                      <div className="p-5">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">
                                {post.author_display_name || '匿名用户'}
                              </span>
                              <span className="text-[11px] px-2 py-0.5 rounded-full border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-gray-500 dark:text-gray-400">
                                示例
                              </span>
                              {post.mood && (
                                <span className="text-xs px-2 py-0.5 rounded-full border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-gray-600 dark:text-gray-300">
                                  {MOOD_OPTIONS.find(m => m.value === post.mood)?.label || String(post.mood)}
                                </span>
                              )}
                            </div>
                            <div className="text-xs text-gray-400 mt-1">
                              {formatTime(post.created_at)}
                            </div>
                          </div>
                          <div className="flex items-center gap-2 shrink-0">
                            <div className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 text-xs text-gray-500 dark:text-gray-400">
                              <Heart className="w-3.5 h-3.5" />
                              {post.like_count}
                            </div>
                            <div className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 text-xs text-gray-500 dark:text-gray-400">
                              <MessageCircle className="w-3.5 h-3.5" />
                              {post.comment_count}
                            </div>
                          </div>
                        </div>

                        <div className="mt-4 text-sm text-gray-800 dark:text-gray-200 leading-relaxed">
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

                        {post.nutrition_snapshot && (
                          <div className="mt-4 rounded-2xl border border-gray-200 dark:border-gray-800 bg-gray-50/70 dark:bg-gray-900/40 p-4">
                            <div className="text-xs font-medium text-gray-600 dark:text-gray-300 mb-2">
                              周摘要（示例）
                            </div>
                            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
                              <div className="rounded-xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 p-3">
                                <div className="text-xs text-gray-500 dark:text-gray-400">总热量</div>
                                <div className="font-semibold text-gray-900 dark:text-gray-100">
                                  {String((post.nutrition_snapshot as any).total_calories ?? '-')}
                                </div>
                              </div>
                              <div className="rounded-xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 p-3">
                                <div className="text-xs text-gray-500 dark:text-gray-400">蛋白</div>
                                <div className="font-semibold text-gray-900 dark:text-gray-100">
                                  {String((post.nutrition_snapshot as any).total_protein ?? '-')}
                                </div>
                              </div>
                              <div className="rounded-xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 p-3">
                                <div className="text-xs text-gray-500 dark:text-gray-400">脂肪</div>
                                <div className="font-semibold text-gray-900 dark:text-gray-100">
                                  {String((post.nutrition_snapshot as any).total_fat ?? '-')}
                                </div>
                              </div>
                              <div className="rounded-xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 p-3">
                                <div className="text-xs text-gray-500 dark:text-gray-400">碳水</div>
                                <div className="font-semibold text-gray-900 dark:text-gray-100">
                                  {String((post.nutrition_snapshot as any).total_carbs ?? '-')}
                                </div>
                              </div>
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      <CreatePostModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        token={token}
        onCreated={() => fetchFeed({ append: false })}
      />
    </div>
  );
}
