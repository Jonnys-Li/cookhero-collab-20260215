import { useEffect, useMemo, useRef, useState } from 'react';
import { Camera, CheckCircle2, Loader2, Plus, Sparkles, Trash2, X } from 'lucide-react';

import type { ImageData } from '../../types/api';
import type { CreateLogRequest, DietLog } from '../../types/diet';
import { createLog, createLogFromText, parseDietLog } from '../../services/api/diet';
import { trackEvent } from '../../services/api/events';

type MealType = 'breakfast' | 'lunch' | 'dinner' | 'snack';

const MEAL_TYPES: MealType[] = ['breakfast', 'lunch', 'dinner', 'snack'];
const MEAL_LABELS: Record<MealType, string> = {
  breakfast: '早餐',
  lunch: '午餐',
  dinner: '晚餐',
  snack: '加餐',
};

type LocalImage = {
  dataUrl: string;
  base64: string;
  mime_type: string;
};

type ParsedItem = {
  food_name: string;
  weight_g?: number;
  unit?: string;
  calories?: number;
  protein?: number;
  fat?: number;
  carbs?: number;
};

function startOfLocalDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

function formatDateYMD(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  const d = startOfLocalDay(date);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function pickDefaultMealType(now: Date): MealType {
  const hour = now.getHours();
  if (hour < 10) return 'breakfast';
  if (hour < 14) return 'lunch';
  if (hour < 20) return 'dinner';
  return 'snack';
}

async function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

function normalizeItems(items: ParsedItem[]): ParsedItem[] {
  const normalized = (items || [])
    .map((i) => ({
      food_name: String(i.food_name || '').trim(),
      weight_g: i.weight_g,
      unit: i.unit,
      calories: i.calories,
      protein: i.protein,
      fat: i.fat,
      carbs: i.carbs,
    }))
    .filter((i) => i.food_name);

  return normalized.length ? normalized : [{ food_name: '' }];
}

export function PhotoLogModal({
  isOpen,
  onClose,
  token,
  defaultDate,
  defaultMealType,
  onSaved,
}: {
  isOpen: boolean;
  onClose: () => void;
  token: string;
  defaultDate: Date;
  defaultMealType?: MealType;
  onSaved?: (log: DietLog) => void | Promise<void>;
}) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [step, setStep] = useState<'select' | 'review'>('select');
  const [images, setImages] = useState<LocalImage[]>([]);
  const [text, setText] = useState('');
  const [logDate, setLogDate] = useState(formatDateYMD(defaultDate));
  const [mealType, setMealType] = useState<MealType>(
    defaultMealType || pickDefaultMealType(new Date())
  );
  const [items, setItems] = useState<ParsedItem[]>([{ food_name: '' }]);

  const [parsing, setParsing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [parseMessage, setParseMessage] = useState<string | null>(null);

  const canParse = useMemo(() => images.length > 0 && !parsing && !saving, [images.length, parsing, saving]);

  useEffect(() => {
    if (!isOpen) return;
    setStep('select');
    setImages([]);
    setText('');
    setItems([{ food_name: '' }]);
    setError(null);
    setSuccess(null);
    setParseMessage(null);
    setLogDate(formatDateYMD(defaultDate));
    setMealType(defaultMealType || pickDefaultMealType(new Date()));
    trackEvent(token, 'photo_log_opened', {
      default_date: formatDateYMD(defaultDate),
    });
  }, [defaultDate, defaultMealType, isOpen, token]);

  const handlePickImages = () => {
    if (parsing || saving) return;
    fileInputRef.current?.click();
  };

  const handleImagesSelected = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    e.target.value = '';
    if (!files.length) return;
    setError(null);
    setSuccess(null);
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
      setImages((prev) => [...prev, ...next]);
    } catch (err) {
      setError(err instanceof Error ? err.message : '读取图片失败，请重试');
      trackEvent(token, 'photo_log_failed', { stage: 'read_image' });
    }
  };

  const handleRemoveImage = (idx: number) => {
    setImages((prev) => prev.filter((_, i) => i !== idx));
  };

  const toApiImages = (): ImageData[] =>
    images.map((img) => ({ data: img.base64, mime_type: img.mime_type }));

  const handleParse = async () => {
    if (!canParse) return;
    setParsing(true);
    setError(null);
    setSuccess(null);
    setParseMessage(null);
    try {
      const res = await parseDietLog(token, {
        images: toApiImages(),
        text: text.trim() || undefined,
      });
      setParseMessage(res.message ? String(res.message) : null);
      setItems(normalizeItems(res.items || []));
      if (res.meal_type && MEAL_TYPES.includes(res.meal_type as MealType)) {
        setMealType(res.meal_type as MealType);
      }
      setStep('review');
      trackEvent(token, 'photo_log_recognized', {
        item_count: Array.isArray(res.items) ? res.items.length : 0,
        meal_type: res.meal_type || mealType,
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : '识别失败，请稍后重试';
      setError(msg);
      trackEvent(token, 'photo_log_failed', { stage: 'parse', message: msg });
    } finally {
      setParsing(false);
    }
  };

  const handleFallbackTextSave = async () => {
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const fallbackText = text.trim() || '拍照记录';
      const log = await createLogFromText(token, {
        text: fallbackText,
        images: toApiImages(),
        log_date: logDate,
        meal_type: mealType,
      });
      setSuccess('已写入记录（未进入编辑）');
      trackEvent(token, 'photo_log_saved', {
        mode: 'fallback_createLogFromText',
        log_date: log.log_date,
        meal_type: log.meal_type,
      });
      await onSaved?.(log);
      onClose();
    } catch (err) {
      const msg = err instanceof Error ? err.message : '写入失败，请稍后重试';
      setError(msg);
      trackEvent(token, 'photo_log_failed', { stage: 'fallback_save', message: msg });
    } finally {
      setSaving(false);
    }
  };

  const handleManualEdit = () => {
    setItems([{ food_name: '' }]);
    setStep('review');
  };

  const handleAddItem = () => {
    setItems((prev) => [...prev, { food_name: '' }]);
  };

  const handleRemoveItem = (idx: number) => {
    setItems((prev) => (prev.length <= 1 ? prev : prev.filter((_, i) => i !== idx)));
  };

  const updateItem = (idx: number, patch: Partial<ParsedItem>) => {
    setItems((prev) => prev.map((it, i) => (i === idx ? { ...it, ...patch } : it)));
  };

  const handleSave = async () => {
    if (saving) return;
    const cleaned = items
      .map((i) => ({
        ...i,
        food_name: String(i.food_name || '').trim(),
      }))
      .filter((i) => i.food_name);

    if (!cleaned.length) {
      setError('请至少填写一个食物条目');
      return;
    }

    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const payload: CreateLogRequest = {
        log_date: logDate,
        meal_type: mealType,
        items: cleaned.map((i) => ({
          food_name: i.food_name,
          weight_g: i.weight_g,
          unit: i.unit,
          calories: i.calories,
          protein: i.protein,
          fat: i.fat,
          carbs: i.carbs,
        })),
        notes: text.trim() ? `拍照补充：${text.trim()}` : undefined,
      };
      const log = await createLog(token, payload);
      setSuccess('已写入饮食记录');
      trackEvent(token, 'photo_log_saved', {
        mode: 'createLog',
        log_date: log.log_date,
        meal_type: log.meal_type,
        item_count: cleaned.length,
      });
      await onSaved?.(log);
      onClose();
    } catch (err) {
      const msg = err instanceof Error ? err.message : '写入失败，请稍后重试';
      setError(msg);
      trackEvent(token, 'photo_log_failed', { stage: 'save', message: msg });
    } finally {
      setSaving(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4">
      <div className="w-full max-w-3xl rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 shadow-xl overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100 dark:border-gray-800">
          <div>
            <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100">
              拍照记录
            </h3>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
              两步流：先识别再编辑确认。识别失败也可直接写入或手动补充。
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg text-gray-500 hover:text-gray-800 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-800"
            disabled={parsing || saving}
            aria-label="Close"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-5 space-y-4">
          {(error || success) && (
            <div
              className={`rounded-xl border px-4 py-3 text-sm ${
                error
                  ? 'border-red-200 bg-red-50 text-red-700 dark:border-red-900/60 dark:bg-red-900/20 dark:text-red-200'
                  : 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/60 dark:bg-emerald-900/20 dark:text-emerald-200'
              }`}
              role={error ? 'alert' : 'status'}
            >
              {error || success}
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <label className="block">
              <span className="text-xs font-medium text-gray-600 dark:text-gray-300">
                日期
              </span>
              <input
                type="date"
                value={logDate}
                onChange={(e) => setLogDate(e.target.value)}
                className="mt-1 w-full rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-200 dark:focus:ring-amber-900/30"
                disabled={parsing || saving}
              />
            </label>
            <label className="block">
              <span className="text-xs font-medium text-gray-600 dark:text-gray-300">
                餐次
              </span>
              <select
                value={mealType}
                onChange={(e) => setMealType(e.target.value as MealType)}
                className="mt-1 w-full rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-200 dark:focus:ring-amber-900/30"
                disabled={parsing || saving}
              >
                {MEAL_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {MEAL_LABELS[t]}
                  </option>
                ))}
              </select>
            </label>
            <div className="flex items-end justify-end gap-2">
              <button
                type="button"
                onClick={() => setStep('select')}
                disabled={parsing || saving}
                className="px-3 py-2 rounded-xl border border-gray-200 dark:border-gray-700 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-70"
              >
                返回选图
              </button>
            </div>
          </div>

          {step === 'select' ? (
            <>
              <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-gray-50/60 dark:bg-gray-900/40 p-4">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                    Step A: 选择图片
                  </div>
                  <div className="flex items-center gap-2">
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept="image/*"
                      capture="environment"
                      multiple
                      onChange={handleImagesSelected}
                      className="hidden"
                    />
                    <button
                      type="button"
                      onClick={handlePickImages}
                      disabled={parsing || saving}
                      className="inline-flex items-center gap-2 rounded-xl bg-amber-600 px-3 py-2 text-sm font-semibold text-white hover:bg-amber-700 disabled:opacity-70"
                    >
                      <Camera className="h-4 w-4" />
                      选择/拍照
                    </button>
                  </div>
                </div>

                {images.length > 0 && (
                  <div className="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-2">
                    {images.map((img, idx) => (
                      <div key={idx} className="relative">
                        <img
                          src={img.dataUrl}
                          alt={`photo-${idx}`}
                          className="h-24 w-full rounded-xl object-cover border border-gray-200 dark:border-gray-800"
                        />
                        <button
                          type="button"
                          onClick={() => handleRemoveImage(idx)}
                          disabled={parsing || saving}
                          className="absolute -top-2 -right-2 bg-white dark:bg-gray-900 text-gray-500 rounded-full shadow p-1 hover:text-red-600"
                          aria-label="Remove image"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}

                <div className="mt-3">
                  <label className="block">
                    <span className="text-xs font-medium text-gray-600 dark:text-gray-300">
                      可选补充文字
                    </span>
                    <textarea
                      value={text}
                      onChange={(e) => setText(e.target.value)}
                      placeholder="例如：训练后的一餐，尽量高蛋白"
                      rows={2}
                      className="mt-1 w-full rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-200 dark:focus:ring-amber-900/30"
                      disabled={parsing || saving}
                    />
                  </label>
                </div>

                <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
                  <div className="text-xs text-gray-500 dark:text-gray-400">
                    最多 4 张图片。识别失败可直接写入或手动编辑。
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      onClick={handleManualEdit}
                      disabled={parsing || saving}
                      className="px-3 py-2 rounded-xl border border-gray-200 dark:border-gray-700 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-70"
                    >
                      手动新增条目
                    </button>
                    <button
                      type="button"
                      onClick={handleFallbackTextSave}
                      disabled={images.length === 0 || parsing || saving}
                      className="px-3 py-2 rounded-xl border border-emerald-200 dark:border-emerald-900/40 text-sm text-emerald-700 dark:text-emerald-200 hover:bg-emerald-50 dark:hover:bg-emerald-900/20 disabled:opacity-70"
                    >
                      直接写入(不编辑)
                    </button>
                    <button
                      type="button"
                      onClick={handleParse}
                      disabled={!canParse}
                      className="inline-flex items-center gap-2 rounded-xl bg-violet-600 px-3 py-2 text-sm font-semibold text-white hover:bg-violet-700 disabled:opacity-70"
                    >
                      {parsing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                      开始识别
                    </button>
                  </div>
                </div>
              </div>

              {parseMessage && (
                <div className="text-xs text-gray-500 dark:text-gray-400">
                  {parseMessage}
                </div>
              )}

              {/* TODO(backend): parse-only endpoint
                  POST /api/v1/diet/logs/parse (auth required)
                  body: { images: ImageData[]; text?: string }
                  response: { items: [...], meal_type?: string, message?: string }
              */}
            </>
          ) : (
            <>
              <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                      Step B: 编辑明细并确认写入
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                      你可以修改识别结果，或手动补充条目。
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={handleAddItem}
                    disabled={saving}
                    className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-70"
                  >
                    <Plus className="h-4 w-4" />
                    新增条目
                  </button>
                </div>

                <div className="mt-4 space-y-3">
                  {items.map((item, idx) => (
                    <div
                      key={idx}
                      className="rounded-2xl border border-gray-100 dark:border-gray-800 bg-gray-50/70 dark:bg-gray-900/40 p-3"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="text-xs font-medium text-gray-600 dark:text-gray-300">
                          条目 {idx + 1}
                        </div>
                        {items.length > 1 && (
                          <button
                            type="button"
                            onClick={() => handleRemoveItem(idx)}
                            disabled={saving}
                            className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-red-600 hover:bg-red-50 dark:text-red-300 dark:hover:bg-red-900/20 disabled:opacity-70"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                            删除
                          </button>
                        )}
                      </div>

                      <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-3">
                        <label className="block">
                          <span className="text-xs text-gray-500">食物名称</span>
                          <input
                            value={item.food_name}
                            onChange={(e) => updateItem(idx, { food_name: e.target.value })}
                            placeholder="例如：牛肉面"
                            className="mt-1 w-full rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-200 dark:focus:ring-emerald-900/30"
                            disabled={saving}
                          />
                        </label>
                        <div className="grid grid-cols-2 gap-3">
                          <label className="block">
                            <span className="text-xs text-gray-500">重量(g)</span>
                            <input
                              value={item.weight_g ?? ''}
                              onChange={(e) =>
                                updateItem(idx, {
                                  weight_g: e.target.value ? Number(e.target.value) : undefined,
                                })
                              }
                              inputMode="decimal"
                              className="mt-1 w-full rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-200 dark:focus:ring-emerald-900/30"
                              disabled={saving}
                            />
                          </label>
                          <label className="block">
                            <span className="text-xs text-gray-500">单位</span>
                            <input
                              value={item.unit ?? ''}
                              onChange={(e) => updateItem(idx, { unit: e.target.value })}
                              placeholder="份/碗/个"
                              className="mt-1 w-full rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-200 dark:focus:ring-emerald-900/30"
                              disabled={saving}
                            />
                          </label>
                        </div>
                      </div>

                      <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-3">
                        <label className="block">
                          <span className="text-xs text-gray-500">kcal</span>
                          <input
                            value={item.calories ?? ''}
                            onChange={(e) =>
                              updateItem(idx, {
                                calories: e.target.value ? Number(e.target.value) : undefined,
                              })
                            }
                            inputMode="numeric"
                            className="mt-1 w-full rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-200 dark:focus:ring-emerald-900/30"
                            disabled={saving}
                          />
                        </label>
                        <label className="block">
                          <span className="text-xs text-gray-500">P(g)</span>
                          <input
                            value={item.protein ?? ''}
                            onChange={(e) =>
                              updateItem(idx, {
                                protein: e.target.value ? Number(e.target.value) : undefined,
                              })
                            }
                            inputMode="decimal"
                            className="mt-1 w-full rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-200 dark:focus:ring-emerald-900/30"
                            disabled={saving}
                          />
                        </label>
                        <label className="block">
                          <span className="text-xs text-gray-500">F(g)</span>
                          <input
                            value={item.fat ?? ''}
                            onChange={(e) =>
                              updateItem(idx, {
                                fat: e.target.value ? Number(e.target.value) : undefined,
                              })
                            }
                            inputMode="decimal"
                            className="mt-1 w-full rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-200 dark:focus:ring-emerald-900/30"
                            disabled={saving}
                          />
                        </label>
                        <label className="block">
                          <span className="text-xs text-gray-500">C(g)</span>
                          <input
                            value={item.carbs ?? ''}
                            onChange={(e) =>
                              updateItem(idx, {
                                carbs: e.target.value ? Number(e.target.value) : undefined,
                              })
                            }
                            inputMode="decimal"
                            className="mt-1 w-full rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-200 dark:focus:ring-emerald-900/30"
                            disabled={saving}
                          />
                        </label>
                      </div>
                    </div>
                  ))}
                </div>

                <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
                  <button
                    type="button"
                    onClick={handleFallbackTextSave}
                    disabled={saving || images.length === 0}
                    className="px-3 py-2 rounded-xl border border-emerald-200 dark:border-emerald-900/40 text-sm text-emerald-700 dark:text-emerald-200 hover:bg-emerald-50 dark:hover:bg-emerald-900/20 disabled:opacity-70"
                  >
                    识别不准？直接写入
                  </button>
                  <button
                    type="button"
                    onClick={handleSave}
                    disabled={saving}
                    className="inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-70"
                  >
                    {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
                    确认写入
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

