import { useEffect, useMemo, useRef, useState } from 'react';
import { ImagePlus, Loader2, Sparkles, X } from 'lucide-react';
import { createCommunityPost, polishCommunityPost } from '../../services/api/community';
import { getWeeklySummary } from '../../services/api/diet';
import { getCapabilities } from '../../services/api/meta';
import { trackEvent } from '../../services/api/events';
import type { WeeklySummary } from '../../types/diet';
import type { CommunityMood, CreateCommunityPostRequest } from '../../types/community';

const TAG_OPTIONS: string[] = [
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

const MOOD_OPTIONS: Array<{ value: CommunityMood; label: string }> = [
  { value: 'happy', label: '开心' },
  { value: 'neutral', label: '平稳' },
  { value: 'anxious', label: '焦虑' },
  { value: 'guilty', label: '内疚' },
  { value: 'tired', label: '疲惫' },
];

type LocalImage = {
  dataUrl: string;
  base64: string;
  mime_type: string;
};

function toSnapshot(summary: WeeklySummary): Record<string, unknown> {
  return {
    week_start_date: summary.week_start_date,
    week_end_date: summary.week_end_date,
    total_calories: summary.total_calories,
    total_protein: summary.total_protein,
    total_fat: summary.total_fat,
    total_carbs: summary.total_carbs,
    avg_daily_calories: summary.avg_daily_calories,
  };
}

async function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

export function CreatePostModal({
  isOpen,
  onClose,
  token,
  onCreated,
}: {
  isOpen: boolean;
  onClose: () => void;
  token: string;
  onCreated: () => void;
}) {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [content, setContent] = useState('');
  const [mood, setMood] = useState<CommunityMood | ''>('');
  const [tags, setTags] = useState<string[]>([]);
  const [isAnonymous, setIsAnonymous] = useState(true);
  const [includeWeeklySummary, setIncludeWeeklySummary] = useState(false);
  const [weeklySnapshot, setWeeklySnapshot] = useState<Record<string, unknown> | null>(null);
  const [images, setImages] = useState<LocalImage[]>([]);

  const [isSaving, setIsSaving] = useState(false);
  const [isPolishing, setIsPolishing] = useState(false);
  const [isLoadingWeekly, setIsLoadingWeekly] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const lastDraftBeforeAIRef = useRef<string | null>(null);
  const [capabilitiesLoading, setCapabilitiesLoading] = useState(false);
  const [communityAiModes, setCommunityAiModes] = useState<string[]>([]);

  const canSubmit = useMemo(() => content.trim().length > 0 && !isSaving, [content, isSaving]);
  const canUsePolish = useMemo(() => communityAiModes.includes('polish'), [communityAiModes]);

  useEffect(() => {
    if (!isOpen) return;
    setError(null);
    setContent('');
    setMood('');
    setTags([]);
    setIsAnonymous(true);
    setIncludeWeeklySummary(false);
    setWeeklySnapshot(null);
    setImages([]);
    setIsSaving(false);
    setIsPolishing(false);
    setIsLoadingWeekly(false);
    lastDraftBeforeAIRef.current = null;
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    if (!token) return;

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
  }, [isOpen, token]);

  const toggleTag = (tag: string) => {
    setTags(prev => {
      if (prev.includes(tag)) return prev.filter(t => t !== tag);
      if (prev.length >= 5) return prev;
      return [...prev, tag];
    });
  };

  const handlePickImages = () => {
    if (isSaving) return;
    fileInputRef.current?.click();
  };

  const handleImagesSelected = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    e.target.value = '';
    if (!files.length) return;

    setError(null);
    try {
      const remaining = Math.max(0, 4 - images.length);
      const selected = files.slice(0, remaining);
      const next: LocalImage[] = [];
      for (const file of selected) {
        const dataUrl = await readFileAsDataUrl(file);
        const base64 = dataUrl.split(',')[1] || '';
        next.push({
          dataUrl,
          base64,
          mime_type: file.type || 'image/jpeg',
        });
      }
      setImages(prev => [...prev, ...next]);
    } catch (err) {
      const msg = err instanceof Error ? err.message : '读取图片失败，请重试';
      setError(msg);
    }
  };

  const handleRemoveImage = (idx: number) => {
    setImages(prev => prev.filter((_, i) => i !== idx));
  };

  const handlePolish = async () => {
    if (!content.trim()) {
      setError('请先写一点打卡内容，再让 AI 帮你润色');
      return;
    }
    if (capabilitiesLoading || !canUsePolish) {
      setError('后端升级中，暂不支持 AI 润色，请稍后刷新重试。');
      return;
    }
    setError(null);
    setIsPolishing(true);
    try {
      lastDraftBeforeAIRef.current = content;
      const polished = await polishCommunityPost(token, content.trim());
      if (!polished.trim()) {
        setError('AI 暂时没有给出有效润色结果，你可以稍后再试');
        return;
      }
      setContent(polished.slice(0, 800));
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'AI 润色失败，请稍后重试';
      setError(msg);
    } finally {
      setIsPolishing(false);
    }
  };

  const handleUndoPolish = () => {
    if (!lastDraftBeforeAIRef.current) return;
    setContent(lastDraftBeforeAIRef.current);
    lastDraftBeforeAIRef.current = null;
  };

  const handleToggleWeekly = async (next: boolean) => {
    setIncludeWeeklySummary(next);
    if (!next) {
      setWeeklySnapshot(null);
      return;
    }
    setIsLoadingWeekly(true);
    setError(null);
    try {
      const summary = await getWeeklySummary(token);
      setWeeklySnapshot(toSnapshot(summary));
    } catch (err) {
      const msg = err instanceof Error ? err.message : '获取周总结失败';
      setError(msg);
      setIncludeWeeklySummary(false);
      setWeeklySnapshot(null);
    } finally {
      setIsLoadingWeekly(false);
    }
  };

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setIsSaving(true);
    setError(null);
    try {
      const payload: CreateCommunityPostRequest = {
        is_anonymous: isAnonymous,
        mood: mood || undefined,
        content: content.trim(),
        tags: tags.length ? tags : undefined,
        images: images.length
          ? images.map(img => ({ data: img.base64, mime_type: img.mime_type }))
          : undefined,
        nutrition_snapshot: includeWeeklySummary ? weeklySnapshot : undefined,
      };
      await createCommunityPost(token, payload);
      trackEvent(token, 'community_post_created', {
        is_anonymous: isAnonymous,
        mood: mood || null,
        tag_count: tags.length,
        has_images: images.length > 0,
        has_weekly_summary: includeWeeklySummary,
      });
      onClose();
      onCreated();
    } catch (err) {
      const msg = err instanceof Error ? err.message : '发帖失败，请稍后重试';
      setError(msg);
    } finally {
      setIsSaving(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4">
      <div className="w-full max-w-2xl rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 shadow-xl overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100 dark:border-gray-800">
          <div>
            <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100">发一条打卡</h3>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
              记录, 共情, 纠偏。内容仅供参考, 不替代专业医疗建议。
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg text-gray-500 hover:text-gray-800 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-800"
            disabled={isSaving}
            aria-label="Close"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-5 space-y-4">
          {error && (
            <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 dark:border-red-900/60 dark:bg-red-900/20 dark:text-red-200 px-4 py-3 text-sm">
              {error}
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <label className="block">
              <span className="text-xs font-medium text-gray-600 dark:text-gray-300">情绪</span>
              <select
                value={mood}
                onChange={(e) => setMood((e.target.value as CommunityMood) || '')}
                className="mt-1 w-full rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-200 dark:focus:ring-orange-900/30"
              >
                <option value="">不选择</option>
                {MOOD_OPTIONS.map(opt => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </label>

            <div className="flex items-end justify-between gap-3">
              <label className="flex items-center gap-2 select-none text-sm text-gray-700 dark:text-gray-200">
                <input
                  type="checkbox"
                  checked={isAnonymous}
                  onChange={(e) => setIsAnonymous(e.target.checked)}
                  className="rounded border-gray-300 dark:border-gray-700"
                />
                匿名发布
              </label>

              <label className="flex items-center gap-2 select-none text-sm text-gray-700 dark:text-gray-200">
                <input
                  type="checkbox"
                  checked={includeWeeklySummary}
                  onChange={(e) => handleToggleWeekly(e.target.checked)}
                  disabled={isLoadingWeekly || isSaving}
                  className="rounded border-gray-300 dark:border-gray-700"
                />
                附带本周总结
                {isLoadingWeekly && <Loader2 className="w-4 h-4 animate-spin text-gray-400" />}
              </label>
            </div>
          </div>

          {includeWeeklySummary && weeklySnapshot && (
            <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-gray-50/70 dark:bg-gray-900/40 p-4">
              <div className="text-xs font-medium text-gray-600 dark:text-gray-300 mb-2">本周摘要</div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
                <div className="rounded-xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 p-3">
                  <div className="text-xs text-gray-500 dark:text-gray-400">总热量</div>
                  <div className="font-semibold text-gray-900 dark:text-gray-100">
                    {String(weeklySnapshot.total_calories ?? '-')}
                  </div>
                </div>
                <div className="rounded-xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 p-3">
                  <div className="text-xs text-gray-500 dark:text-gray-400">蛋白</div>
                  <div className="font-semibold text-gray-900 dark:text-gray-100">
                    {String(weeklySnapshot.total_protein ?? '-')}
                  </div>
                </div>
                <div className="rounded-xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 p-3">
                  <div className="text-xs text-gray-500 dark:text-gray-400">脂肪</div>
                  <div className="font-semibold text-gray-900 dark:text-gray-100">
                    {String(weeklySnapshot.total_fat ?? '-')}
                  </div>
                </div>
                <div className="rounded-xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 p-3">
                  <div className="text-xs text-gray-500 dark:text-gray-400">碳水</div>
                  <div className="font-semibold text-gray-900 dark:text-gray-100">
                    {String(weeklySnapshot.total_carbs ?? '-')}
                  </div>
                </div>
              </div>
            </div>
          )}

          <div>
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-medium text-gray-600 dark:text-gray-300">内容</span>
              <div className="flex items-center gap-2">
                {lastDraftBeforeAIRef.current && (
                  <button
                    type="button"
                    onClick={handleUndoPolish}
                    disabled={isPolishing || isSaving || capabilitiesLoading}
                    className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
                  >
                    撤销
                  </button>
                )}
                <button
                  type="button"
                  onClick={handlePolish}
                  disabled={isPolishing || isSaving || capabilitiesLoading || !canUsePolish}
                  title={
                    capabilitiesLoading
                      ? '正在检测后端能力...'
                      : (!canUsePolish ? '后端升级中，稍后刷新' : '点击润色（不会自动消耗）')
                  }
                  className={`inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full border transition-colors ${
                    isPolishing || isSaving || capabilitiesLoading || !canUsePolish
                      ? 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 text-gray-400 opacity-60 cursor-not-allowed'
                      : 'border-orange-200 dark:border-orange-800 bg-orange-50 dark:bg-orange-900/20 text-orange-700 dark:text-orange-300 hover:bg-orange-100/60 dark:hover:bg-orange-900/30'
                  }`}
                >
                  {isPolishing || capabilitiesLoading ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Sparkles className="w-3.5 h-3.5" />
                  )}
                  AI 润色
                </button>
              </div>
            </div>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              rows={5}
              placeholder="比如：今天有点焦虑但还是按计划吃了晚餐，想听听大家怎么缓解压力..."
              className="w-full rounded-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-4 py-3 text-sm leading-relaxed focus:outline-none focus:ring-2 focus:ring-orange-200 dark:focus:ring-orange-900/30"
            />
            <div className="mt-2 flex items-center justify-between text-xs text-gray-400">
              <span>最多 800 字</span>
              <span>{content.length}/800</span>
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-gray-600 dark:text-gray-300">标签 (最多 5 个)</span>
              <span className="text-xs text-gray-400">{tags.length}/5</span>
            </div>
            <div className="flex flex-wrap gap-2">
              {TAG_OPTIONS.map(tag => {
                const active = tags.includes(tag);
                return (
                  <button
                    type="button"
                    key={tag}
                    onClick={() => toggleTag(tag)}
                    className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${
                      active
                        ? 'border-orange-300 bg-orange-50 text-orange-700 dark:border-orange-700 dark:bg-orange-900/20 dark:text-orange-200'
                        : 'border-gray-200 bg-white text-gray-600 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300 dark:hover:bg-gray-800'
                    }`}
                  >
                    {tag}
                  </button>
                );
              })}
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-gray-600 dark:text-gray-300">图片 (最多 4 张)</span>
              <button
                type="button"
                onClick={handlePickImages}
                disabled={isSaving || images.length >= 4}
                className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors disabled:opacity-50"
              >
                <ImagePlus className="w-3.5 h-3.5" />
                添加图片
              </button>
            </div>

            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              multiple
              onChange={handleImagesSelected}
              className="hidden"
            />

            {images.length > 0 && (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {images.map((img, idx) => (
                  <div key={idx} className="relative rounded-2xl overflow-hidden border border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-900">
                    <img src={img.dataUrl} alt={`upload-${idx}`} className="w-full h-28 object-cover" />
                    <button
                      type="button"
                      onClick={() => handleRemoveImage(idx)}
                      className="absolute top-2 right-2 p-1 rounded-full bg-black/50 text-white hover:bg-black/70"
                      aria-label="Remove"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="px-5 py-4 border-t border-gray-100 dark:border-gray-800 bg-gray-50/40 dark:bg-gray-950/20 flex items-center justify-end gap-2">
          <button
            onClick={onClose}
            disabled={isSaving}
            className="px-4 py-2 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-50"
          >
            取消
          </button>
          <button
            onClick={handleSubmit}
            disabled={!canSubmit}
            className="px-4 py-2 rounded-xl text-sm font-medium bg-orange-500 text-white hover:bg-orange-600 disabled:opacity-50 disabled:hover:bg-orange-500 inline-flex items-center gap-2"
          >
            {isSaving && <Loader2 className="w-4 h-4 animate-spin" />}
            发布
          </button>
        </div>
      </div>
    </div>
  );
}
