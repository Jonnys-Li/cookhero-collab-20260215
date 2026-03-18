/**
 * Diet Management Page
 * Weekly diet plan view with meal planning and logging
 */

import { useCallback, useEffect, useRef, useState, type ChangeEvent } from 'react';
import { useLocation } from 'react-router-dom';
import {
  Calendar,
  ChevronLeft,
  ChevronRight,
  Plus,
  Check,
  Edit2,
  Trash2,
  Utensils,
  Coffee,
  Moon,
  Cookie,
  Loader2,
  X,
  Flame,
  Beef,
  Croissant,
  Droplet,
  Camera,
} from 'lucide-react';
import { useAuth } from '../../contexts';
import {
  getPlanByWeek,
  addMealToPlan,
  updateMeal,
  deleteMeal,
  markMealEaten,
  getLogsByDate,
  createLogFromText,
  recognizeMealFromImage,
  updateLog,
  deleteLog,
  getWeeklySummary,
  getDietBudget,
  getShoppingList,
} from '../../services/api/diet';
import { trackEvent } from '../../services/api/events';
import { WeeklyDeviationCorrectionCard } from '../../components/diet/WeeklyDeviationCorrectionCard';
import { WeeklyShareToCommunityCard } from '../../components/diet/WeeklyShareToCommunityCard';
import { PhotoLogModal } from '../../components/diet/PhotoLogModal';
import { ShoppingListPanel } from '../../components/diet/ShoppingListPanel';
import type {
  Dish,
  DietPlan,
  DietPlanMeal,
  DietLog,
  WeeklySummary,
  DailySummary,
  DietBudgetSnapshot,
  EmotionExemptionStatus,
  ShoppingListResponse,
} from '../../types';

// Meal type icons
const MEAL_ICONS: Record<string, React.ReactNode> = {
  breakfast: <Coffee className="w-4 h-4" />,
  lunch: <Utensils className="w-4 h-4" />,
  dinner: <Moon className="w-4 h-4" />,
  snack: <Cookie className="w-4 h-4" />,
};

const MEAL_LABELS: Record<string, string> = {
  breakfast: '早餐',
  lunch: '午餐',
  dinner: '晚餐',
  snack: '加餐',
};

const MEAL_TYPES = ['breakfast', 'lunch', 'dinner', 'snack'];

const DAY_LABELS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];

/**
 * Get week start date (Monday) for a given date
 */
function startOfLocalDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

function getWeekStartDate(date: Date): Date {
  const d = startOfLocalDay(date);
  const day = d.getDay();
  const diff = d.getDate() - day + (day === 0 ? -6 : 1);
  const weekStart = new Date(d);
  weekStart.setDate(diff);
  return startOfLocalDay(weekStart);
}

/**
 * Format date as YYYY-MM-DD
 */
function formatDate(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  const d = startOfLocalDay(date);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function isEmotionExemptionActive(status?: EmotionExemptionStatus | null): boolean {
  if (!status) return false;
  return Boolean(status.active ?? status.is_active);
}

function parseLocalYMD(dateStr: string): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dateStr);
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const date = new Date(year, month - 1, day);
  if (
    date.getFullYear() !== year ||
    date.getMonth() !== month - 1 ||
    date.getDate() !== day
  ) {
    return null;
  }
  return date;
}

/**
 * Format date as M月D日
 */
function formatDateShort(date: Date): string {
  return `${date.getMonth() + 1}月${date.getDate()}日`;
}

/**
 * Add days to a date
 */
function addDays(date: Date, days: number): Date {
  const result = startOfLocalDay(date);
  result.setDate(result.getDate() + days);
  return result;
}

function getDayIndex(date: Date): number {
  const day = date.getDay();
  return day === 0 ? 6 : day - 1;
}

type MaybeNumber = number | null | undefined;

function formatMaybeNumber(
  value: MaybeNumber,
  fractionDigits: number,
  placeholder = '-'
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return placeholder;
  return value.toFixed(fractionDigits);
}

/**
 * Meal Card Component
 */
interface MealCardProps {
  meal?: DietPlanMeal;
  mealType: string;
  date: Date;
  logs?: DietLog[];
  onAddMeal: () => void;
  onEditMeal: (meal: DietPlanMeal) => void;
  onDeleteMeal: (mealId: string) => void;
  onMarkEaten: (mealId: string) => void;
}

function MealCard({
  meal,
  mealType,
  date,
  logs,
  onAddMeal,
  onEditMeal,
  onDeleteMeal,
  onMarkEaten,
}: MealCardProps) {
  const mealLogs = logs?.filter(log => log.meal_type === mealType) || [];
  const hasLog = mealLogs.length > 0;
  const actualTotals = mealLogs.reduce(
    (acc, log) => {
      if (log.total_calories !== null && log.total_calories !== undefined) {
        acc.calories += log.total_calories;
        acc.hasCalories = true;
      }
      if (log.total_protein !== null && log.total_protein !== undefined) {
        acc.protein += log.total_protein;
        acc.hasProtein = true;
      }
      if (log.total_fat !== null && log.total_fat !== undefined) {
        acc.fat += log.total_fat;
        acc.hasFat = true;
      }
      if (log.total_carbs !== null && log.total_carbs !== undefined) {
        acc.carbs += log.total_carbs;
        acc.hasCarbs = true;
      }
      return acc;
    },
    {
      calories: 0,
      protein: 0,
      fat: 0,
      carbs: 0,
      hasCalories: false,
      hasProtein: false,
      hasFat: false,
      hasCarbs: false,
    }
  );
  const isToday = formatDate(date) === formatDate(new Date());
  const isPast = date < new Date() && !isToday;

  return (
    <div
      className={`
        relative p-3 rounded-xl border transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md
        ${hasLog
          ? 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800'
          : meal
          ? 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700'
          : 'bg-gray-50 dark:bg-gray-900/50 border-dashed border-gray-300 dark:border-gray-700'
        }
        ${isToday ? 'ring-2 ring-blue-400 dark:ring-blue-500' : ''}
      `}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-1.5 text-gray-600 dark:text-gray-400">
          {MEAL_ICONS[mealType]}
          <span className="text-xs font-medium">{MEAL_LABELS[mealType]}</span>
        </div>
        {hasLog && (
          <Check className="w-4 h-4 text-green-500" />
        )}
      </div>

      {/* Content */}
      {meal ? (
        <div className="space-y-2">
          {/* Dishes */}
          <div className="text-sm text-gray-800 dark:text-gray-200">
            {meal.dishes?.map((dish, idx) => (
              <div key={idx} className="mb-1 last:mb-0">
                <div className="truncate">
                  {dish.name}
                  {dish.calories !== null && dish.calories !== undefined && (
                    <span className="text-xs text-gray-500 ml-1">
                      ({dish.calories}kcal)
                    </span>
                  )}
                </div>
                <div className="text-[11px] text-gray-500 dark:text-gray-400">
                  P {dish.protein?.toFixed(1) || '-'} · F {dish.fat?.toFixed(1) || '-'} · C {dish.carbs?.toFixed(1) || '-'}
                  {dish.nutrition_source && (
                    <span className="ml-1">· {dish.nutrition_source}</span>
                  )}
                </div>
              </div>
            )) || <span className="text-gray-400">无菜品</span>}
          </div>

          {/* Nutrition Summary */}
          <div className="text-xs text-gray-500 dark:text-gray-400 space-y-1">
            <div>
              计划 {meal.total_calories !== null && meal.total_calories !== undefined ? meal.total_calories.toFixed(0) : '-'} kcal · P {meal.total_protein?.toFixed(1) || '-'} · F {meal.total_fat?.toFixed(1) || '-'} · C {meal.total_carbs?.toFixed(1) || '-'}
            </div>
            {hasLog && (
              <div className="text-green-600 dark:text-green-400">
                实际 {actualTotals.hasCalories ? actualTotals.calories.toFixed(0) : '-'} kcal · P {actualTotals.hasProtein ? actualTotals.protein.toFixed(1) : '-'} · F {actualTotals.hasFat ? actualTotals.fat.toFixed(1) : '-'} · C {actualTotals.hasCarbs ? actualTotals.carbs.toFixed(1) : '-'}
              </div>
            )}
          </div>

          {/* Actions */}
          <div className="flex items-center gap-1 pt-1">
            {!hasLog && !isPast && (
              <button
                onClick={() => onMarkEaten(meal.id)}
                className="p-1 text-green-600 hover:bg-green-100 dark:hover:bg-green-900/30 rounded"
                title="标记为已吃"
              >
                <Check className="w-3.5 h-3.5" />
              </button>
            )}
            <button
              onClick={() => onEditMeal(meal)}
              className="p-1 text-blue-600 hover:bg-blue-100 dark:hover:bg-blue-900/30 rounded"
              title="编辑"
            >
              <Edit2 className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => onDeleteMeal(meal.id)}
              className="p-1 text-red-600 hover:bg-red-100 dark:hover:bg-red-900/30 rounded"
              title="删除"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      ) : (
        <button
          onClick={onAddMeal}
          className="w-full py-4 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
          title="添加计划餐次（预先规划）"
        >
          <Plus className="w-5 h-5 mx-auto" />
          <span className="text-xs">规划</span>
        </button>
      )}
    </div>
  );
}

interface LogCardProps {
  logs?: DietLog[];
  mealType: string;
  date: Date;
  highlighted?: boolean;
  onAddLog: () => void;
  onEditLog: (log: DietLog) => void;
  onDeleteLog: (logId: string) => void;
}

function LogCard({ logs, mealType, date, highlighted = false, onAddLog, onEditLog, onDeleteLog }: LogCardProps) {
  const mealLogs = logs?.filter(log => log.meal_type === mealType) || [];
  const hasLog = mealLogs.length > 0;
  const isToday = formatDate(date) === formatDate(new Date());
  const totals = mealLogs.reduce(
    (acc, log) => {
      if (log.total_calories !== null && log.total_calories !== undefined) {
        acc.calories += log.total_calories;
        acc.hasCalories = true;
      }
      if (log.total_protein !== null && log.total_protein !== undefined) {
        acc.protein += log.total_protein;
        acc.hasProtein = true;
      }
      if (log.total_fat !== null && log.total_fat !== undefined) {
        acc.fat += log.total_fat;
        acc.hasFat = true;
      }
      if (log.total_carbs !== null && log.total_carbs !== undefined) {
        acc.carbs += log.total_carbs;
        acc.hasCarbs = true;
      }
      return acc;
    },
    {
      calories: 0,
      protein: 0,
      fat: 0,
      carbs: 0,
      hasCalories: false,
      hasProtein: false,
      hasFat: false,
      hasCarbs: false,
    }
  );
  const formatLogTotals = (log: DietLog) => {
    const caloriesText = formatMaybeNumber(log.total_calories, 0);
    const proteinText = formatMaybeNumber(log.total_protein, 1);
    const fatText = formatMaybeNumber(log.total_fat, 1);
    const carbsText = formatMaybeNumber(log.total_carbs, 1);
    return `实际 ${caloriesText} kcal · P ${proteinText} · F ${fatText} · C ${carbsText}`;
  };

  return (
    <div
      className={`relative p-3 rounded-xl border transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md ${
        hasLog
          ? 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700'
          : 'bg-gray-50 dark:bg-gray-900/50 border-dashed border-gray-300 dark:border-gray-700'
      } ${isToday ? 'ring-2 ring-amber-400/60 dark:ring-amber-500/60' : ''} ${
        highlighted ? 'ring-2 ring-emerald-400 dark:ring-emerald-500 animate-pulse' : ''
      }`}
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-1.5 text-gray-600 dark:text-gray-400">
          {MEAL_ICONS[mealType]}
          <span className="text-xs font-medium">{MEAL_LABELS[mealType]}</span>
        </div>
        {hasLog && <Check className="w-4 h-4 text-emerald-500" />}
      </div>

        {hasLog ? (
          <div className="space-y-3">
            <div className="space-y-2">
              {mealLogs.map(log => (
                <div
                  key={log.id}
                  className="rounded-lg border border-gray-100 dark:border-gray-700/60 bg-gray-50/70 dark:bg-gray-900/40 p-2"
                >
                  <div className="text-sm text-gray-800 dark:text-gray-200">
                    {log.items?.length ? (
                      log.items.map((item, idx) => (
                        <div key={idx} className="truncate">
                          {item.food_name}
                          {item.calories !== null && item.calories !== undefined && (
                            <span className="text-xs text-gray-500 ml-1">({item.calories}kcal)</span>
                          )}
                        </div>
                      ))
                    ) : (
                      <span className="text-gray-400">暂无食物明细</span>
                    )}
                  </div>
                  <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    {formatLogTotals(log)}
                  </div>
                  {log.notes && (
                    <div className="text-xs text-gray-500 mt-1">
                      {log.notes}
                    </div>
                  )}
                  <div className="flex items-center gap-1 pt-1">
                    <button
                      onClick={() => onEditLog(log)}
                      className="p-1 text-blue-600 hover:bg-blue-100 dark:hover:bg-blue-900/30 rounded"
                      title="编辑记录"
                    >
                      <Edit2 className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={() => onDeleteLog(log.id)}
                      className="p-1 text-red-600 hover:bg-red-100 dark:hover:bg-red-900/30 rounded"
                      title="删除记录"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
            <div className="text-xs text-gray-500 dark:text-gray-400">
              合计 {totals.hasCalories ? totals.calories.toFixed(0) : '-'} kcal · P {totals.hasProtein ? totals.protein.toFixed(1) : '-'} · F {totals.hasFat ? totals.fat.toFixed(1) : '-'} · C {totals.hasCarbs ? totals.carbs.toFixed(1) : '-'}
            </div>
          </div>
        ) : (
        <button
          onClick={onAddLog}
          className="w-full py-4 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
        >
          <Plus className="w-5 h-5 mx-auto" />
          <span className="text-xs">记录</span>
        </button>
      )}
    </div>
  );
}

/**
 * Add/Edit Meal Modal
 */
type MealDishInput = Dish;

interface MealModalProps {
  isOpen: boolean;
  onClose: () => void;
  token?: string | null;
  onSave: (data: {
    dishes: MealDishInput[];
    notes?: string;
  }) => Promise<void>;
  initialData?: DietPlanMeal;
  mealType: string;
  date: Date;
}

function MealModal({
  isOpen,
  onClose,
  token,
  onSave,
  initialData,
  mealType,
  date,
}: MealModalProps) {
  const [dishes, setDishes] = useState<MealDishInput[]>([{ name: '' }]);
  const [notes, setNotes] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [isRecognizing, setIsRecognizing] = useState(false);
  const [recognizeMessage, setRecognizeMessage] = useState<string | null>(null);
  const [recognizeError, setRecognizeError] = useState<string | null>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);
  const dayLabel = DAY_LABELS[getDayIndex(date)];

  useEffect(() => {
    if (initialData?.dishes) {
      setDishes(
        initialData.dishes.map(d => ({
          name: d.name,
          weight_g: d.weight_g,
          unit: d.unit,
          calories: d.calories,
          protein: d.protein,
          fat: d.fat,
          carbs: d.carbs,
        }))
      );
      setNotes(initialData.notes || '');
    } else {
      setDishes([{ name: '' }]);
      setNotes('');
    }
    setRecognizeMessage(null);
    setRecognizeError(null);
  }, [initialData, isOpen]);

  const readFileAsDataUrl = (file: File) =>
    new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });

  const handleOpenImagePicker = () => {
    if (isRecognizing || isSaving) return;
    imageInputRef.current?.click();
  };

  const handleRecognizeImage = async (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files || []);
    event.target.value = '';
    if (!files.length) return;

    if (!token) {
      setRecognizeError('登录状态已失效，请重新登录后再试');
      setRecognizeMessage(null);
      return;
    }

    const selectedFiles = files.slice(0, 4);
    setIsRecognizing(true);
    setRecognizeError(null);
    setRecognizeMessage(null);

    try {
      const images = await Promise.all(
        selectedFiles.map(async file => {
          const dataUrl = await readFileAsDataUrl(file);
          const base64 = dataUrl.split(',')[1] || '';
          return {
            data: base64,
            mime_type: file.type || 'image/jpeg',
          };
        })
      );

      const response = await recognizeMealFromImage(token, {
        images,
        context_text: notes.trim() || undefined,
      });

      const recognizedDishes: MealDishInput[] = (response.dishes || [])
        .map(dish => ({
          name: (dish.name || '').trim(),
          calories: dish.calories,
          protein: dish.protein,
          fat: dish.fat,
          carbs: dish.carbs,
          weight_g: dish.weight_g,
          unit: dish.unit,
        }))
        .filter(dish => dish.name);

      if (!recognizedDishes.length) {
        setRecognizeMessage(response.message || '未识别到清晰食物，请手动补充');
        return;
      }

      setDishes(prev => [...prev, ...recognizedDishes]);
      setRecognizeMessage(`识别完成，已追加 ${recognizedDishes.length} 个菜品`);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : 'AI 识别失败，请稍后重试';
      setRecognizeError(message);
    } finally {
      setIsRecognizing(false);
    }
  };

  const handleSave = async () => {
    const validDishes = dishes.filter(d => d.name.trim());
    if (validDishes.length === 0) return;

    setIsSaving(true);
    try {
      await onSave({ dishes: validDishes, notes: notes || undefined });
      onClose();
    } catch (error) {
      console.error('Failed to save meal:', error);
    } finally {
      setIsSaving(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-xl w-full max-w-md mx-4 p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            {initialData ? '编辑计划餐次' : '添加计划餐次'} - {MEAL_LABELS[mealType]} - {dayLabel}
          </h3>
          <button
            onClick={onClose}
            className="p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Dishes */}
        <div className="space-y-3 mb-4">
          <div className="flex items-center justify-between">
            <label className="text-sm font-medium text-gray-700 dark:text-gray-300">菜品列表</label>
            <input
              ref={imageInputRef}
              type="file"
              accept="image/*"
              capture="environment"
              multiple
              onChange={handleRecognizeImage}
              className="hidden"
            />
            <button
              type="button"
              onClick={handleOpenImagePicker}
              disabled={isRecognizing || isSaving}
              className="inline-flex items-center gap-1.5 rounded-lg border border-blue-200 px-2.5 py-1 text-xs text-blue-600 hover:bg-blue-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-blue-700 dark:text-blue-300 dark:hover:bg-blue-900/20"
            >
              {isRecognizing ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Camera className="h-3.5 w-3.5" />
              )}
              AI拍照识别
            </button>
          </div>
          {recognizeError && (
            <p className="text-xs text-red-500">{recognizeError}</p>
          )}
          {!recognizeError && recognizeMessage && (
            <p className="text-xs text-gray-500 dark:text-gray-400">{recognizeMessage}</p>
          )}
          {dishes.map((dish, idx) => (
            <div key={idx} className="flex gap-2">
              <input
                type="text"
                value={dish.name}
                onChange={e => {
                  const newDishes = [...dishes];
                  newDishes[idx].name = e.target.value;
                  setDishes(newDishes);
                }}
                placeholder="菜品名称"
                className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500"
              />
              <input
                type="number"
                value={dish.calories ?? ''}
                onChange={e => {
                  const newDishes = [...dishes];
                  newDishes[idx].calories = e.target.value ? Number(e.target.value) : undefined;
                  setDishes(newDishes);
                }}
                placeholder="kcal"
                className="w-20 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500"
              />
              {dishes.length > 1 && (
                <button
                  onClick={() => setDishes(dishes.filter((_, i) => i !== idx))}
                  className="p-2 text-red-500 hover:bg-red-100 dark:hover:bg-red-900/30 rounded-lg"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              )}
            </div>
          ))}
          <button
            onClick={() => setDishes([...dishes, { name: '' }])}
            className="text-sm text-blue-600 hover:text-blue-700 dark:text-blue-400"
          >
            + 添加菜品
          </button>
        </div>

        {/* Notes */}
        <div className="mb-4">
          <label className="text-sm font-medium text-gray-700 dark:text-gray-300">备注</label>
          <textarea
            value={notes}
            onChange={e => setNotes(e.target.value)}
            placeholder="可选备注..."
            rows={2}
            className="w-full mt-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500"
          />
        </div>

        {/* Actions */}
        <div className="flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2 text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
          >
            取消
          </button>
          <button
            onClick={handleSave}
            disabled={isSaving || !dishes.some(d => d.name.trim())}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {isSaving && <Loader2 className="w-4 h-4 animate-spin" />}
            保存
          </button>
        </div>
      </div>
    </div>
  );
}

/**
 * Quick Log Modal - Log from text
 */
interface QuickLogModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (text: string, mealType?: string, images?: Array<{ data: string; mime_type: string }>) => Promise<void>;
  date: Date;
  initialMealType?: string;
}

function QuickLogModal({ isOpen, onClose, onSave, date, initialMealType }: QuickLogModalProps) {
  const [text, setText] = useState('');
  const [mealType, setMealType] = useState('');
  const [images, setImages] = useState<Array<{ data: string; mime_type: string; preview: string }>>([]);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    setMealType(initialMealType || '');
  }, [isOpen, initialMealType]);

  useEffect(() => {
    if (!isOpen) {
      setImages([]);
    }
  }, [isOpen]);

  const readFileAsDataUrl = (file: File) =>
    new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });

  const handleImageChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files || []);
    if (!files.length) return;

    const remaining = 4 - images.length;
    const selected = files.slice(0, remaining);
    const newImages = await Promise.all(
      selected.map(async file => {
        const dataUrl = await readFileAsDataUrl(file);
        const base64 = dataUrl.split(',')[1] || '';
        return {
          data: base64,
          mime_type: file.type || 'image/jpeg',
          preview: dataUrl,
        };
      })
    );

    setImages(prev => [...prev, ...newImages]);
    event.target.value = '';
  };

  const handleSave = async () => {
    if (!text.trim()) return;

    setIsSaving(true);
    try {
      await onSave(
        text,
        mealType || undefined,
        images.map(image => ({ data: image.data, mime_type: image.mime_type }))
      );
      setText('');
      setMealType('');
      setImages([]);
      onClose();
    } catch (error) {
      console.error('Failed to log meal:', error);
    } finally {
      setIsSaving(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-xl w-full max-w-md mx-4 p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            记录实际饮食 - {formatDateShort(date)}
          </h3>
          <button
            onClick={onClose}
            className="p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
              描述你吃了什么
            </label>
            <textarea
              value={text}
              onChange={e => setText(e.target.value)}
              placeholder="例如：今天中午吃了一碗牛肉面和一个苹果"
              rows={3}
              className="w-full mt-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500"
            />
            <p className="text-xs text-gray-500 mt-1">AI 会自动识别食物并估算营养数据</p>
          </div>

          <div>
            <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
              添加图片（可选，最多 4 张）
            </label>
            <input
              type="file"
              accept="image/*"
              multiple
              onChange={handleImageChange}
              className="mt-2 block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-amber-100/70 file:text-amber-800 hover:file:bg-amber-200/80"
            />
            {images.length > 0 && (
              <div className="mt-3 grid grid-cols-4 gap-2">
                {images.map((image, idx) => (
                  <div key={idx} className="relative">
                    <img
                      src={image.preview}
                      alt={`upload-${idx}`}
                      className="h-16 w-full rounded-lg object-cover"
                    />
                    <button
                      type="button"
                      onClick={() => setImages(prev => prev.filter((_, i) => i !== idx))}
                      className="absolute -top-2 -right-2 bg-white text-gray-500 rounded-full shadow p-0.5"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div>
            <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
              餐次（可选，AI 可自动推断）
            </label>
            <select
              value={mealType}
              onChange={e => setMealType(e.target.value)}
              className="w-full mt-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500"
            >
              <option value="">自动推断</option>
              {MEAL_TYPES.map(type => (
                <option key={type} value={type}>{MEAL_LABELS[type]}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="flex justify-end gap-2 mt-6">
          <button
            onClick={onClose}
            className="px-4 py-2 text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
          >
            取消
          </button>
          <button
            onClick={handleSave}
            disabled={isSaving || !text.trim()}
            className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {isSaving && <Loader2 className="w-4 h-4 animate-spin" />}
            记录
          </button>
        </div>
      </div>
    </div>
  );
}

interface EditLogModalProps {
  isOpen: boolean;
  log?: DietLog | null;
  onClose: () => void;
  onSave: (data: { items: Array<{ food_name: string; weight_g?: number; unit?: string; calories?: number; protein?: number; fat?: number; carbs?: number }>; notes?: string }) => Promise<void>;
}

function EditLogModal({ isOpen, log, onClose, onSave }: EditLogModalProps) {
  const [items, setItems] = useState<Array<{ food_name: string; weight_g?: number; unit?: string; calories?: number; protein?: number; fat?: number; carbs?: number }>>([{ food_name: '' }]);
  const [notes, setNotes] = useState('');
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    if (log?.items?.length) {
      setItems(log.items.map(item => ({
        food_name: item.food_name,
        weight_g: item.weight_g,
        unit: item.unit,
        calories: item.calories,
        protein: item.protein,
        fat: item.fat,
        carbs: item.carbs,
      })));
    } else {
      setItems([{ food_name: '' }]);
    }
    setNotes(log?.notes || '');
  }, [log, isOpen]);

  const handleSave = async () => {
    const validItems = items.filter(item => item.food_name.trim());
    if (!validItems.length) return;
    setIsSaving(true);
    try {
      await onSave({ items: validItems, notes: notes || undefined });
      onClose();
    } catch (error) {
      console.error('Failed to update log:', error);
    } finally {
      setIsSaving(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-xl w-full max-w-2xl mx-4 p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            编辑饮食记录 - {log?.log_date ? formatDateShort(new Date(`${log.log_date}T00:00:00`)) : ''}
          </h3>
          <button
            onClick={onClose}
            className="p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="space-y-4">
          <div className="space-y-2">
            <label className="text-sm font-medium text-gray-700 dark:text-gray-300">食物列表</label>
            {items.map((item, idx) => (
              <div key={idx} className="grid grid-cols-1 md:grid-cols-[2fr_repeat(4,minmax(0,1fr))_auto] gap-2">
                <input
                  type="text"
                  value={item.food_name}
                  onChange={e => {
                    const next = [...items];
                    next[idx].food_name = e.target.value;
                    setItems(next);
                  }}
                  placeholder="食物名称"
                  className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-emerald-500"
                />
                <input
                  type="number"
                  value={item.calories ?? ''}
                  onChange={e => {
                    const next = [...items];
                    next[idx].calories = e.target.value ? Number(e.target.value) : undefined;
                    setItems(next);
                  }}
                  placeholder="kcal"
                  className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-emerald-500"
                />
                <input
                  type="number"
                  value={item.protein ?? ''}
                  onChange={e => {
                    const next = [...items];
                    next[idx].protein = e.target.value ? Number(e.target.value) : undefined;
                    setItems(next);
                  }}
                  placeholder="蛋白 g"
                  className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-emerald-500"
                />
                <input
                  type="number"
                  value={item.fat ?? ''}
                  onChange={e => {
                    const next = [...items];
                    next[idx].fat = e.target.value ? Number(e.target.value) : undefined;
                    setItems(next);
                  }}
                  placeholder="脂肪 g"
                  className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-emerald-500"
                />
                <input
                  type="number"
                  value={item.carbs ?? ''}
                  onChange={e => {
                    const next = [...items];
                    next[idx].carbs = e.target.value ? Number(e.target.value) : undefined;
                    setItems(next);
                  }}
                  placeholder="碳水 g"
                  className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-emerald-500"
                />
                {items.length > 1 && (
                  <button
                    onClick={() => setItems(items.filter((_, i) => i !== idx))}
                    className="p-2 text-red-500 hover:bg-red-100 dark:hover:bg-red-900/30 rounded-lg"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                )}
              </div>
            ))}
            <button
              onClick={() => setItems([...items, { food_name: '' }])}
              className="text-sm text-emerald-600 hover:text-emerald-700 dark:text-emerald-400"
            >
              + 添加食物
            </button>
          </div>

          <div>
            <label className="text-sm font-medium text-gray-700 dark:text-gray-300">备注</label>
            <textarea
              value={notes}
              onChange={e => setNotes(e.target.value)}
              placeholder="可选备注..."
              rows={2}
              className="w-full mt-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-emerald-500"
            />
          </div>
        </div>

        <div className="flex justify-end gap-2 mt-6">
          <button
            onClick={onClose}
            className="px-4 py-2 text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
          >
            取消
          </button>
          <button
            onClick={handleSave}
            disabled={isSaving || !items.some(item => item.food_name.trim())}
            className="px-4 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {isSaving && <Loader2 className="w-4 h-4 animate-spin" />}
            保存
          </button>
        </div>
      </div>
    </div>
  );
}

/**
 * Weekly Summary Panel
 */
interface SummaryPanelProps {
  summary?: WeeklySummary;
  isLoading: boolean;
}

function SummaryPanel({ summary, isLoading }: SummaryPanelProps) {
  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
      </div>
    );
  }

  const totalCalories = summary?.total_calories ?? null;
  const totalProtein = summary?.total_protein ?? null;
  const totalFat = summary?.total_fat ?? null;
  const totalCarbs = summary?.total_carbs ?? null;
  const avgCalories = summary?.avg_daily_calories ?? null;
  const averageFromTotal = (total: number | null) => (total === null ? null : total / 7);
  const formatAverageLine = (
    average: number | null,
    unit: string,
    fractionDigits = 0
  ) => {
    const averageText =
      average === null ? '--' : `${average.toFixed(fractionDigits)} ${unit}`;
    return `日均 ${averageText}`;
  };

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      <div className="bg-white dark:bg-gray-800 rounded-2xl p-4 border border-amber-100 dark:border-amber-900/50 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md">
        <div className="flex items-center gap-2 text-amber-600/80 dark:text-amber-300 mb-2">
          <Flame className="w-4 h-4" />
          <span className="text-xs">本周热量</span>
        </div>
        <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">
          {totalCalories !== null ? totalCalories.toLocaleString() : '-'}
          <span className="text-sm font-normal text-gray-500 ml-1">kcal</span>
        </div>
        <div className="text-xs text-gray-500 mt-1">
          {formatAverageLine(avgCalories, 'kcal')}
        </div>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-2xl p-4 border border-blue-100 dark:border-blue-900/50 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md">
        <div className="flex items-center gap-2 text-blue-500/80 dark:text-blue-300 mb-2">
          <Beef className="w-4 h-4" />
          <span className="text-xs">蛋白质</span>
        </div>
        <div className="text-2xl font-bold text-blue-600 dark:text-blue-400">
          {totalProtein !== null ? totalProtein.toFixed(1) : '-'}
          <span className="text-sm font-normal text-gray-500 ml-1">g</span>
        </div>
        <div className="text-xs text-gray-500 mt-2">
          {formatAverageLine(averageFromTotal(totalProtein), 'g', 1)}
        </div>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-2xl p-4 border border-emerald-100 dark:border-emerald-900/50 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md">
        <div className="flex items-center gap-2 text-emerald-500/80 dark:text-emerald-300 mb-2">
          <Droplet className="w-4 h-4" />
          <span className="text-xs">脂肪</span>
        </div>
        <div className="text-2xl font-bold text-emerald-600 dark:text-emerald-400">
          {totalFat !== null ? totalFat.toFixed(1) : '-'}
          <span className="text-sm font-normal text-gray-500 ml-1">g</span>
        </div>
        <div className="text-xs text-gray-500 mt-2">
          {formatAverageLine(averageFromTotal(totalFat), 'g', 1)}
        </div>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-2xl p-4 border border-orange-100 dark:border-orange-900/50 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md">
        <div className="flex items-center gap-2 text-orange-500/80 dark:text-orange-300 mb-2">
          <Croissant className="w-4 h-4" />
          <span className="text-xs">碳水</span>
        </div>
        <div className="text-2xl font-bold text-orange-600 dark:text-orange-400">
          {totalCarbs !== null ? totalCarbs.toFixed(1) : '-'}
          <span className="text-sm font-normal text-gray-500 ml-1">g</span>
        </div>
        <div className="text-xs text-gray-500 mt-2">
          {formatAverageLine(averageFromTotal(totalCarbs), 'g', 1)}
        </div>
      </div>
    </div>
  );
}

/**
 * Main Diet Management Page
 */
export default function DietManagementPage() {
  const { token } = useAuth();
  const location = useLocation();
  const [currentWeekStart, setCurrentWeekStart] = useState(() => getWeekStartDate(new Date()));
  const [plan, setPlan] = useState<DietPlan | null>(null);
  const [logs, setLogs] = useState<Map<string, DietLog[]>>(new Map());
  const [weeklySummary, setWeeklySummary] = useState<WeeklySummary | null>(null);
  const [dailySummaries, setDailySummaries] = useState<Record<string, DailySummary>>({});
  const [budgetSnapshot, setBudgetSnapshot] = useState<DietBudgetSnapshot | null>(null);
  const [shoppingList, setShoppingList] = useState<ShoppingListResponse | null>(null);
  const [budgetLoading, setBudgetLoading] = useState(false);
  const [budgetError, setBudgetError] = useState<string | null>(null);
  const [budgetHighlighted, setBudgetHighlighted] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [highlightKey, setHighlightKey] = useState<string | null>(null);

  // Modal states
  const [mealModalOpen, setMealModalOpen] = useState(false);
  const [mealModalData, setMealModalData] = useState<{
    meal?: DietPlanMeal;
    mealType: string;
    date: Date;
  } | null>(null);
  const [quickLogModalOpen, setQuickLogModalOpen] = useState(false);
  const [quickLogDate, setQuickLogDate] = useState(new Date());
  const [activeDayIndex, setActiveDayIndex] = useState(0);
  const [viewMode, setViewMode] = useState<'plan' | 'log'>('plan');
  const [quickLogMealType, setQuickLogMealType] = useState<string | undefined>(undefined);
  const [editLogModalOpen, setEditLogModalOpen] = useState(false);
  const [editLogData, setEditLogData] = useState<DietLog | null>(null);
  const [photoLogModalOpen, setPhotoLogModalOpen] = useState(false);

  // Deep-link support: /agent/diet#diet-week-progress
  // For weekly progress actions in Agent cards, we jump here and default to "log" view.
  useEffect(() => {
    if (location.hash !== '#diet-week-progress') return;
    setViewMode('log');
    if (isLoading) return;
    const anchor = document.getElementById('diet-week-progress');
    if (!anchor) return;
    window.requestAnimationFrame(() => {
      anchor.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }, [location.hash, isLoading]);

  // Deep-link support: /agent/diet#diet-budget
  // Used by emotion-support budget adjust card to show immediate change visibility.
  useEffect(() => {
    if (location.hash !== '#diet-budget') return;
    // Default to today's day when deep-linking budget view.
    const today = new Date();
    setCurrentWeekStart(getWeekStartDate(today));
    setActiveDayIndex(getDayIndex(today));
    const anchor = document.getElementById('diet-budget');
    if (!anchor) return;
    window.requestAnimationFrame(() => {
      anchor.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
    setBudgetHighlighted(true);
    const timer = window.setTimeout(() => setBudgetHighlighted(false), 2200);
    return () => window.clearTimeout(timer);
  }, [location.hash]);

  // Focus/highlight support from Agent "record meal" flow:
  // /agent/diet?focus_date=YYYY-MM-DD&focus_meal=lunch#diet-week-progress
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const focusDateStr = params.get('focus_date');
    if (!focusDateStr) return;
    const focusMeal = params.get('focus_meal') || '';

    const focusDate = parseLocalYMD(focusDateStr);
    if (!focusDate) return;

    setCurrentWeekStart(getWeekStartDate(focusDate));
    setActiveDayIndex(getDayIndex(focusDate));
    setViewMode('log');
    if (focusMeal) {
      setHighlightKey(`${focusDateStr}-${focusMeal}`);
      const timer = window.setTimeout(() => setHighlightKey(null), 4500);
      return () => window.clearTimeout(timer);
    }
  }, [location.search]);

  // Fetch plan and logs for the current week
  const fetchData = useCallback(async () => {
    if (!token) return;

    setIsLoading(true);
    setError(null);

    try {
      const weekStartStr = formatDate(currentWeekStart);

      // Fetch plan
      const planData = await getPlanByWeek(token, weekStartStr);
      setPlan(planData.plan);

      // Fetch logs for each day of the week
      const newLogs = new Map<string, DietLog[]>();
      for (let i = 0; i < 7; i++) {
        const date = addDays(currentWeekStart, i);
        const dateStr = formatDate(date);
        try {
          const logsData = await getLogsByDate(token, dateStr);
          newLogs.set(dateStr, logsData.logs);
        } catch {
          // Ignore errors for individual days
        }
      }
      setLogs(newLogs);

      // Fetch summary
      try {
        const summaryData = await getWeeklySummary(token, weekStartStr);
        setWeeklySummary(summaryData);
      } catch {
        // Ignore
      }

      try {
        const shoppingListData = await getShoppingList(token, weekStartStr);
        setShoppingList(shoppingListData);
      } catch {
        setShoppingList(null);
      }

    } catch (err) {
      setError(err instanceof Error ? err.message : '加载数据失败');
    } finally {
      setIsLoading(false);
    }
  }, [token, currentWeekStart]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Fetch budget snapshot for the active day (default: today via deep-link, otherwise the selected day)
  useEffect(() => {
    if (!token) return;
    const dateStr = formatDate(addDays(currentWeekStart, activeDayIndex));
    setBudgetLoading(true);
    setBudgetError(null);
    getDietBudget(token, dateStr)
      .then((snapshot) => setBudgetSnapshot(snapshot))
      .catch((err) => {
        console.error('Failed to load diet budget:', err);
        setBudgetSnapshot(null);
        setBudgetError(err instanceof Error ? err.message : '加载预算失败');
      })
      .finally(() => setBudgetLoading(false));
  }, [token, currentWeekStart, activeDayIndex]);

  useEffect(() => {
    const weeklyData = weeklySummary?.daily_data;
    if (!weeklyData) {
      setDailySummaries({});
      return;
    }

    const summaries: Record<string, DailySummary> = {};
    Object.entries(weeklyData).forEach(([date, data]) => {
      summaries[date] = {
        date,
        total_calories: data.calories,
        total_protein: data.protein,
        total_fat: data.fat,
        total_carbs: data.carbs,
        meals_logged: data.meals,
        log_count: data.meals.length,
      };
    });
    setDailySummaries(summaries);
  }, [weeklySummary]);

  // Navigate weeks
  const goToPreviousWeek = () => {
    setCurrentWeekStart(addDays(currentWeekStart, -7));
  };

  const goToNextWeek = () => {
    setCurrentWeekStart(addDays(currentWeekStart, 7));
  };

  const goToCurrentWeek = () => {
    setCurrentWeekStart(getWeekStartDate(new Date()));
  };

  // Get meal for a specific day and type
  const getMealForDayAndType = (dayOfWeek: number, mealType: string): DietPlanMeal | undefined => {
    const dateStr = formatDate(addDays(currentWeekStart, dayOfWeek));
    return plan?.meals?.find(
      m => m.plan_date === dateStr && m.meal_type === mealType
    );
  };

  // Handle add meal
  const handleAddMeal = (date: Date, mealType: string) => {
    setMealModalData({ mealType, date });
    setMealModalOpen(true);
  };

  // Handle edit meal
  const handleEditMeal = (meal: DietPlanMeal) => {
    setMealModalData({
      meal,
      mealType: meal.meal_type,
      date: new Date(`${meal.plan_date}T00:00:00`),
    });
    setMealModalOpen(true);
  };

  // Handle save meal
  const handleSaveMeal = async (data: {
    dishes: Array<{
      name: string;
      weight_g?: number;
      unit?: string;
      calories?: number;
      protein?: number;
      fat?: number;
      carbs?: number;
    }>;
    notes?: string;
  }) => {
    if (!token || !mealModalData) return;

    if (mealModalData.meal) {
      // Update existing meal
      await updateMeal(token, mealModalData.meal.id, {
        dishes: data.dishes,
        notes: data.notes,
      });
    } else {
      // Add new meal
      await addMealToPlan(token, {
        plan_date: formatDate(mealModalData.date),
        meal_type: mealModalData.mealType,
        dishes: data.dishes,
        notes: data.notes,
      });
      trackEvent(token, 'diet_plan_meal_created', {
        plan_date: formatDate(mealModalData.date),
        meal_type: mealModalData.mealType,
        dish_count: data.dishes?.length ?? 0,
      });
    }

    await fetchData();
  };

  // Handle delete meal
  const handleDeleteMeal = async (mealId: string) => {
    if (!token) return;
    if (!confirm('确定要删除这个餐次吗？')) return;

    await deleteMeal(token, mealId);
    await fetchData();
  };

  // Handle mark eaten
  const handleMarkEaten = async (mealId: string) => {
    if (!token) return;
    const log = await markMealEaten(token, mealId, {});
    trackEvent(token, 'diet_log_created', {
      source: 'mark_meal_eaten',
      log_date: log?.log_date,
      meal_type: log?.meal_type,
    });
    await fetchData();
  };

  // Handle quick log
  const handleQuickLog = async (
    text: string,
    mealType?: string,
    images?: Array<{ data: string; mime_type: string }>
  ) => {
    if (!token) return;
    const log = await createLogFromText(token, {
      text,
      log_date: formatDate(quickLogDate),
      meal_type: mealType,
      images,
    });
    trackEvent(token, 'diet_log_created', {
      source: images?.length ? 'ai_image' : 'ai_text',
      log_date: log?.log_date,
      meal_type: log?.meal_type ?? mealType,
      has_images: Boolean(images?.length),
    });
    await fetchData();
  };

  const handleEditLog = (log: DietLog) => {
    setEditLogData(log);
    setEditLogModalOpen(true);
  };

  const handleDeleteLog = async (logId: string) => {
    if (!token) return;
    if (!confirm('确定要删除这条记录吗？')) return;
    await deleteLog(token, logId);
    await fetchData();
  };

  const handleUpdateLog = async (data: { items: Array<{ food_name: string; weight_g?: number; unit?: string; calories?: number; protein?: number; fat?: number; carbs?: number }>; notes?: string }) => {
    if (!token || !editLogData) return;
    await updateLog(token, editLogData.id, {
      items: data.items,
      notes: data.notes,
    });
    await fetchData();
  };

  // Open quick log modal for a specific date
  const openQuickLogForDate = (date: Date, mealType?: string) => {
    const index = Math.max(
      0,
      Math.min(6, Math.floor((date.getTime() - currentWeekStart.getTime()) / (1000 * 60 * 60 * 24)))
    );
    setActiveDayIndex(index);
    setQuickLogMealType(mealType);
    setQuickLogDate(date);
    setQuickLogModalOpen(true);
  };

  const isCurrentWeek = formatDate(currentWeekStart) === formatDate(getWeekStartDate(new Date()));

  const getDayPlanTotals = (dateStr: string) => {
    const dayMeals = plan?.meals?.filter(meal => meal.plan_date === dateStr) || [];
    const totals = dayMeals.reduce(
      (acc, meal) => {
        if (meal.total_calories !== null && meal.total_calories !== undefined) {
          acc.calories += meal.total_calories;
          acc.hasCalories = true;
        }
        if (meal.total_protein !== null && meal.total_protein !== undefined) {
          acc.protein += meal.total_protein;
          acc.hasProtein = true;
        }
        if (meal.total_fat !== null && meal.total_fat !== undefined) {
          acc.fat += meal.total_fat;
          acc.hasFat = true;
        }
        if (meal.total_carbs !== null && meal.total_carbs !== undefined) {
          acc.carbs += meal.total_carbs;
          acc.hasCarbs = true;
        }
        return acc;
      },
      {
        calories: 0,
        protein: 0,
        fat: 0,
        carbs: 0,
        hasCalories: false,
        hasProtein: false,
        hasFat: false,
        hasCarbs: false,
      }
    );
    return {
      calories: totals.hasCalories ? totals.calories : null,
      protein: totals.hasProtein ? totals.protein : null,
      fat: totals.hasFat ? totals.fat : null,
      carbs: totals.hasCarbs ? totals.carbs : null,
    };
  };

  const getDayActualTotals = (dateStr: string) => {
    const dayLogs = logs.get(dateStr) || [];
    const totals = dayLogs.reduce(
      (acc, log) => {
        if (log.total_calories !== null && log.total_calories !== undefined) {
          acc.calories += log.total_calories;
          acc.hasCalories = true;
        }
        if (log.total_protein !== null && log.total_protein !== undefined) {
          acc.protein += log.total_protein;
          acc.hasProtein = true;
        }
        if (log.total_fat !== null && log.total_fat !== undefined) {
          acc.fat += log.total_fat;
          acc.hasFat = true;
        }
        if (log.total_carbs !== null && log.total_carbs !== undefined) {
          acc.carbs += log.total_carbs;
          acc.hasCarbs = true;
        }
        return acc;
      },
      {
        calories: 0,
        protein: 0,
        fat: 0,
        carbs: 0,
        hasCalories: false,
        hasProtein: false,
        hasFat: false,
        hasCarbs: false,
      }
    );
    return {
      calories: totals.hasCalories ? totals.calories : null,
      protein: totals.hasProtein ? totals.protein : null,
      fat: totals.hasFat ? totals.fat : null,
      carbs: totals.hasCarbs ? totals.carbs : null,
    };
  };

  const getActiveDayDate = () => addDays(currentWeekStart, activeDayIndex);
  const activeDayDate = getActiveDayDate();
  const activeDayDateStr = formatDate(activeDayDate);
  const emotionExemptionStatus =
    budgetSnapshot?.emotion_exemption || weeklySummary?.emotion_exemption || null;
  const emotionExemptionActive = isEmotionExemptionActive(emotionExemptionStatus);
  const emotionExemptionMessage =
    emotionExemptionActive
      ? (emotionExemptionStatus?.summary ||
        `${formatDateShort(activeDayDate)} 已进入情绪豁免，今日将暂停预算调整与下一餐纠偏引导。`)
      : null;

  return (
    <div className="flex-1 overflow-auto p-4 md:p-6">
      <div className="max-w-7xl mx-auto space-y-6">
        {/* Header */}
        <div className="rounded-3xl border border-amber-100/70 dark:border-amber-900/40 bg-gradient-to-br from-orange-50 via-white to-amber-50 dark:from-slate-900 dark:via-slate-900 dark:to-slate-800 p-6 shadow-sm">
          <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-6">
            <div>
              <div className="flex items-center gap-3 text-amber-700 dark:text-amber-200">
                <div className="p-2 rounded-2xl bg-amber-100/70 dark:bg-amber-900/40">
                  <Calendar className="w-6 h-6" />
                </div>
                <div>
                  <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                    饮食管理
                  </h1>
                  <p className="text-sm text-amber-700/80 dark:text-amber-200/80 mt-1">
                    结合计划与实际，追踪每周营养执行度
                  </p>
                </div>
              </div>
            </div>

            {/* Week Navigation */}
            <div className="flex flex-wrap items-center gap-3">
              <button
                onClick={goToPreviousWeek}
                className="p-2 rounded-xl border border-amber-200/60 dark:border-amber-900/40 hover:bg-amber-100/70 dark:hover:bg-amber-900/20 transition-colors"
              >
                <ChevronLeft className="w-5 h-5" />
              </button>
              <div className="text-center min-w-[200px]">
                <div className="font-semibold text-gray-900 dark:text-gray-100">
                  {formatDateShort(currentWeekStart)} - {formatDateShort(addDays(currentWeekStart, 6))}
                </div>
                {!isCurrentWeek && (
                  <button
                    onClick={goToCurrentWeek}
                    className="text-xs text-amber-600 dark:text-amber-300 hover:underline"
                  >
                    返回本周
                  </button>
                )}
              </div>
              <button
                onClick={goToNextWeek}
                className="p-2 rounded-xl border border-amber-200/60 dark:border-amber-900/40 hover:bg-amber-100/70 dark:hover:bg-amber-900/20 transition-colors"
              >
                <ChevronRight className="w-5 h-5" />
              </button>
            </div>
          </div>

        </div>

        {/* Error */}
        {error && (
          <div className="p-4 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-lg text-red-600 dark:text-red-400">
            {error}
          </div>
        )}

        {/* Weekly Summary */}
        <SummaryPanel
          summary={weeklySummary || undefined}
          isLoading={isLoading}
        />

        {/* Deviation -> Correction (default entry) */}
        {token && !emotionExemptionActive && (
          <WeeklyDeviationCorrectionCard
            token={token}
            weekStartDate={formatDate(currentWeekStart)}
            planMeals={plan?.meals}
            weeklySummary={weeklySummary}
            onApplied={fetchData}
          />
        )}

        {token && emotionExemptionMessage && (
          <div className="rounded-3xl border border-amber-200/70 dark:border-amber-900/40 bg-gradient-to-br from-amber-50 via-white to-rose-50/40 dark:from-slate-900 dark:via-slate-900 dark:to-slate-800 p-5 shadow-sm">
            <div className="inline-flex items-center gap-2 rounded-full border border-amber-200 bg-amber-100/70 px-3 py-1 text-xs font-medium text-amber-800 dark:border-amber-900/40 dark:bg-amber-900/20 dark:text-amber-200">
              当前周视图
            </div>
            <div className="mt-3 text-sm font-semibold text-gray-900 dark:text-gray-100">
              情绪豁免已生效
            </div>
            <div className="mt-1 text-sm text-gray-600 dark:text-gray-300">
              {emotionExemptionMessage}
            </div>
          </div>
        )}

        {/* Share Weekly Summary (share = review) */}
        {token && (
          <WeeklyShareToCommunityCard
            token={token}
            weeklySummary={weeklySummary}
          />
        )}

        <ShoppingListPanel shoppingList={shoppingList} />

        {/* Daily Focus */}
        <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-5 shadow-sm transition-all duration-200 hover:shadow-md">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">日度执行视图</h2>
              <p className="text-xs text-gray-500 mt-1">选择日期查看计划与实际营养差异</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {token && (
                <button
                  type="button"
                  onClick={() => setPhotoLogModalOpen(true)}
                  className="inline-flex items-center gap-2 rounded-full border border-amber-200 bg-amber-100/60 px-3 py-1.5 text-xs font-semibold text-amber-800 hover:bg-amber-100 dark:border-amber-900/40 dark:bg-amber-500/10 dark:text-amber-200"
                  title="拍照记录（先识别再编辑确认）"
                >
                  <Camera className="h-3.5 w-3.5" />
                  拍照记录
                </button>
              )}
              {DAY_LABELS.map((label, idx) => {
                const active = idx === activeDayIndex;
                return (
                  <button
                    key={label}
                    onClick={() => setActiveDayIndex(idx)}
                    className={`px-3 py-1 rounded-full border text-xs transition-colors ${
                      active
                        ? 'border-amber-400 bg-amber-100/70 text-amber-800 dark:border-amber-500/60 dark:bg-amber-500/20 dark:text-amber-200'
                        : 'border-gray-200 dark:border-gray-700 text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800'
                    }`}
                  >
                    {label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Daily Budget Panel (visible feedback for emotion-support adjustments) */}
          <div
            id="diet-budget"
            className={`mt-5 rounded-2xl border bg-gradient-to-br from-emerald-50/70 via-white to-amber-50/40 dark:from-emerald-900/15 dark:via-slate-900 dark:to-slate-900 p-4 transition-all ${
              budgetHighlighted
                ? 'border-emerald-200 dark:border-emerald-800 ring-2 ring-emerald-400 dark:ring-emerald-500 animate-pulse'
                : 'border-gray-100 dark:border-gray-800'
            }`}
          >
            {(() => {
              const date = getActiveDayDate();
              const dateStr = formatDate(date);
              const actualTotals = getDayActualTotals(dateStr);
              const budgetGoal =
                budgetSnapshot?.effective_goal === null ||
                budgetSnapshot?.effective_goal === undefined
                  ? null
                  : Number(budgetSnapshot.effective_goal);
              const remainingDelta =
                budgetGoal !== null && actualTotals.calories !== null
                  ? budgetGoal - actualTotals.calories
                  : null;
              const remainingLine = (() => {
                if (remainingDelta === null) return '今日剩余 -- kcal';
                const absText = Math.abs(remainingDelta).toFixed(0);
                if (remainingDelta >= 0) return `今日剩余 ${absText} kcal`;
                return `已超出 ${absText} kcal`;
              })();
              const remainingClass =
                remainingDelta === null
                  ? 'text-gray-600 dark:text-gray-300'
                  : remainingDelta >= 0
                    ? 'text-emerald-700 dark:text-emerald-300'
                    : 'text-rose-700 dark:text-rose-300';
              const goalSourceText = (() => {
                const source = budgetSnapshot?.goal_source;
                if (source === 'explicit') return '用户目标';
                if (source === 'avg7d') return '近7天均值';
                if (source === 'default1800') return '系统默认 1800';
                return source ? String(source) : '未标注';
              })();
              const todayAdjustment =
                budgetSnapshot?.today_adjustment === null ||
                budgetSnapshot?.today_adjustment === undefined
                  ? null
                  : Number(budgetSnapshot.today_adjustment);
              const todayAdjText =
                todayAdjustment === null
                  ? '--'
                  : `${todayAdjustment >= 0 ? '+' : ''}${todayAdjustment}`;

              return (
                <>
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div>
                      <div className="flex flex-wrap items-center gap-2 text-xs text-emerald-700 dark:text-emerald-200">
                        <span>当日预算 · {formatDateShort(date)}</span>
                        {emotionExemptionActive && dateStr === activeDayDateStr && (
                          <span className="rounded-full border border-amber-200 bg-amber-100/80 px-2.5 py-1 text-[11px] font-medium text-amber-800 dark:border-amber-900/40 dark:bg-amber-900/20 dark:text-amber-200">
                            情绪豁免期
                          </span>
                        )}
                      </div>
                      <div className="mt-2 text-2xl font-bold text-gray-900 dark:text-gray-100">
                        {budgetSnapshot?.effective_goal ?? '--'}{' '}
                        <span className="text-sm font-normal text-gray-500 ml-1">kcal</span>
                      </div>
                      <div className="mt-1 text-xs text-gray-600 dark:text-gray-300">
                        基线 {budgetSnapshot?.base_goal ?? '--'} kcal · 今日调整 {todayAdjText} kcal
                        <span className="ml-1 text-[11px] text-gray-500 dark:text-gray-400">
                          （来源：{goalSourceText}
                          {budgetSnapshot?.goal_seeded ? '，系统兜底' : ''}）
                        </span>
                      </div>
                      <div className={`mt-2 text-xs ${remainingClass}`}>{remainingLine}</div>
                      {emotionExemptionActive && dateStr === activeDayDateStr && (
                        <div className="mt-3 rounded-xl border border-amber-200/70 bg-amber-50/80 px-3 py-2 text-xs text-amber-800 dark:border-amber-900/40 dark:bg-amber-900/20 dark:text-amber-200">
                          情绪豁免中：今天优先稳住节奏，不触发下一餐纠偏入口。
                        </div>
                      )}
                    </div>

                    <div className="rounded-xl border border-emerald-100 dark:border-emerald-900/50 bg-white/70 dark:bg-gray-900/50 px-3 py-2">
                      <div className="text-[11px] text-gray-500">剩余可调</div>
                      <div className="mt-0.5 text-sm font-semibold text-emerald-700 dark:text-emerald-300">
                        {budgetSnapshot?.remaining_adjustment_cap ?? '--'} kcal
                      </div>
                      <div className="text-[11px] text-gray-500">
                        单日上限 {budgetSnapshot?.adjustment_cap ?? '--'} kcal
                      </div>
                    </div>
                  </div>

                  {budgetLoading && (
                    <div className="mt-3 inline-flex items-center gap-2 text-xs text-gray-600 dark:text-gray-300">
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      正在加载预算...
                    </div>
                  )}
                  {budgetError && !budgetLoading && (
                    <div className="mt-3 inline-flex items-start gap-2 rounded-lg border border-red-200 dark:border-red-900/60 bg-red-50 dark:bg-red-900/20 px-2.5 py-2 text-xs text-red-600 dark:text-red-300">
                      <span className="font-medium">预算加载失败</span>
                      <span className="text-red-600/90 dark:text-red-300/90">{budgetError}</span>
                    </div>
                  )}
                </>
              );
            })()}
          </div>

          <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-4">
            {(() => {
              const date = getActiveDayDate();
              const dateStr = formatDate(date);
              const planTotals = getDayPlanTotals(dateStr);
              const actualTotals = getDayActualTotals(dateStr);
              const daySummary = dailySummaries[dateStr];
              const actualLogs = logs.get(dateStr) || [];
              const adherence =
                planTotals.calories !== null &&
                planTotals.calories > 0 &&
                actualTotals.calories !== null
                  ? Math.min(100, (actualTotals.calories / planTotals.calories) * 100)
                  : 0;

              return (
                <>
                  <div className="rounded-2xl border border-gray-100 dark:border-gray-800 bg-amber-50/60 dark:bg-amber-900/10 p-4">
                    <div className="text-xs text-amber-700 dark:text-amber-200">
                      {formatDateShort(date)} · 计划目标
                    </div>
                    <div className="mt-2 text-lg font-semibold text-gray-900 dark:text-gray-100">
                      {planTotals.calories !== null ? `${planTotals.calories.toFixed(0)} kcal` : '未设置'}
                    </div>
                    <div className="text-xs text-gray-500 mt-1">
                      蛋白 {planTotals.protein !== null ? planTotals.protein.toFixed(1) : '--'}g · 脂肪{' '}
                      {planTotals.fat !== null ? planTotals.fat.toFixed(1) : '--'}g · 碳水{' '}
                      {planTotals.carbs !== null ? planTotals.carbs.toFixed(1) : '--'}g
                    </div>
                    <div className="mt-3 text-xs text-gray-500">
                      计划餐次 {plan?.meals?.filter(meal => meal.plan_date === dateStr).length || 0} 餐
                    </div>
                  </div>

                  <div className="rounded-2xl border border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-900 p-4">
                    <div className="text-xs text-gray-500">实际摄入</div>
                    <div className="mt-2 text-lg font-semibold text-gray-900 dark:text-gray-100">
                      {actualTotals.calories !== null ? `${actualTotals.calories.toFixed(0)} kcal` : '暂无记录'}
                    </div>
                    <div className="text-xs text-gray-500 mt-1">
                      蛋白 {actualTotals.protein !== null ? actualTotals.protein.toFixed(1) : '--'}g · 脂肪{' '}
                      {actualTotals.fat !== null ? actualTotals.fat.toFixed(1) : '--'}g · 碳水{' '}
                      {actualTotals.carbs !== null ? actualTotals.carbs.toFixed(1) : '--'}g
                    </div>
                    <div className="mt-3 text-xs text-gray-500">
                      记录餐次 {actualLogs.length} · 完成度{' '}
                      {planTotals.calories !== null &&
                      planTotals.calories > 0 &&
                      actualTotals.calories !== null
                        ? adherence.toFixed(0)
                        : 0}
                      %
                    </div>
                    <div className="mt-3 h-2 rounded-full bg-gray-100 dark:bg-gray-800">
                      <div
                        className="h-2 rounded-full bg-gradient-to-r from-amber-400 via-orange-400 to-rose-400"
                        style={{ width: `${Math.min(100, adherence)}%` }}
                      />
                    </div>
                    <div className="mt-3 text-xs text-gray-500">
                      {daySummary?.meals_logged?.length ? `已记录 ${daySummary.meals_logged.join('、')}` : '未记录餐次'}
                    </div>
                  </div>
                </>
              );
            })()}
          </div>
        </div>

        {token && (
          <PhotoLogModal
            isOpen={photoLogModalOpen}
            onClose={() => setPhotoLogModalOpen(false)}
            token={token}
            defaultDate={activeDayDate}
            onSaved={() => fetchData()}
          />
        )}

        <div id="diet-week-progress" className="flex flex-wrap items-center justify-between gap-3">
          <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">本周明细</div>
          <div className="flex rounded-full border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-sm transition-shadow hover:shadow">
            <button
              onClick={() => setViewMode('plan')}
              className={`px-4 py-1.5 text-xs rounded-full transition-colors ${
                viewMode === 'plan'
                  ? 'bg-amber-100 text-amber-800 dark:bg-amber-500/20 dark:text-amber-200'
                  : 'text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800'
              }`}
            >
              计划视图
            </button>
            <button
              onClick={() => setViewMode('log')}
              className={`px-4 py-1.5 text-xs rounded-full transition-colors ${
                viewMode === 'log'
                  ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-500/20 dark:text-emerald-200'
                  : 'text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800'
              }`}
            >
              记录视图
            </button>
          </div>
        </div>

        {/* Week Grid */}
        {isLoading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="w-8 h-8 animate-spin text-gray-400" />
          </div>
        ) : (
          <div className="pt-2 overflow-x-auto">
            <div className="min-w-[900px]">
              {/* Day Headers */}
              <div className="grid grid-cols-7 gap-2 mb-2">
                {DAY_LABELS.map((label, idx) => {
                  const date = addDays(currentWeekStart, idx);
                  const isToday = formatDate(date) === formatDate(new Date());
                  return (
                    <div
                      key={idx}
                      className={`
                        text-center py-2 rounded-2xl border transition-all duration-200 hover:-translate-y-0.5 hover:shadow-sm
                        ${isToday
                          ? 'bg-amber-100/80 dark:bg-amber-900/30 text-amber-800 dark:text-amber-200 font-semibold border-amber-200 dark:border-amber-700'
                          : 'text-gray-600 dark:text-gray-400 border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-900'
                        }
                      `}
                    >
                      <div>{label}</div>
                      <div className="text-xs">{formatDateShort(date)}</div>
                      <button
                        onClick={() => openQuickLogForDate(date)}
                        className="mt-1 text-xs text-green-600 dark:text-green-400 hover:underline"
                        title="记录实际吃了什么"
                      >
                        记录饮食
                      </button>
                    </div>
                  );
                })}
              </div>

              {/* Meal Rows */}
              {MEAL_TYPES.map(mealType => (
                <div key={mealType} className="grid grid-cols-7 gap-2 mb-2">
                  {[0, 1, 2, 3, 4, 5, 6].map(dayOfWeek => {
                    const date = addDays(currentWeekStart, dayOfWeek);
                    const dateStr = formatDate(date);
                      return viewMode === 'plan' ? (
                        <MealCard
                          key={`${dayOfWeek}-${mealType}`}
                          meal={getMealForDayAndType(dayOfWeek, mealType)}
                          mealType={mealType}
                          date={date}
                          logs={logs.get(dateStr)}
                          onAddMeal={() => handleAddMeal(date, mealType)}
                          onEditMeal={handleEditMeal}
                          onDeleteMeal={handleDeleteMeal}
                          onMarkEaten={handleMarkEaten}
                        />
                      ) : (
                        <LogCard
                          key={`${dayOfWeek}-${mealType}`}
                          logs={logs.get(dateStr)}
                          mealType={mealType}
                          date={date}
                          highlighted={highlightKey === `${dateStr}-${mealType}`}
                          onAddLog={() => openQuickLogForDate(date, mealType)}
                          onEditLog={handleEditLog}
                          onDeleteLog={handleDeleteLog}
                        />
                      );
                    })}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Modals */}
      <MealModal
        isOpen={mealModalOpen}
        onClose={() => {
          setMealModalOpen(false);
          setMealModalData(null);
        }}
        token={token}
        onSave={handleSaveMeal}
        initialData={mealModalData?.meal}
        mealType={mealModalData?.mealType || 'lunch'}
        date={mealModalData?.date || currentWeekStart}
      />

      <QuickLogModal
        isOpen={quickLogModalOpen}
        onClose={() => {
          setQuickLogModalOpen(false);
          setQuickLogMealType(undefined);
        }}
        onSave={handleQuickLog}
        date={quickLogDate}
        initialMealType={quickLogMealType}
      />

      <EditLogModal
        isOpen={editLogModalOpen}
        log={editLogData}
        onClose={() => {
          setEditLogModalOpen(false);
          setEditLogData(null);
        }}
        onSave={handleUpdateLog}
      />
    </div>
  );
}
