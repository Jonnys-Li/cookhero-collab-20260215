/**
 * Diet types for frontend
 */

import type { ImageData } from './api';

export interface Dish {
  name: string;
  weight_g?: number;
  unit?: string;
  calories?: number;
  protein?: number;
  fat?: number;
  carbs?: number;
  nutrition_source?: string;
  nutrition_confidence?: number;
}

export interface DietPlanMeal {
  id: string;
  plan_date: string;
  meal_type: string;
  dishes?: Dish[];
  total_calories?: number;
  total_protein?: number;
  total_fat?: number;
  total_carbs?: number;
  notes?: string;
}

export interface DietPlan {
  user_id: string;
  week_start_date: string;
  meals?: DietPlanMeal[];
}

export interface FoodItem {
  id: string;
  log_id: string;
  food_name: string;
  weight_g?: number;
  unit?: string;
  calories?: number;
  protein?: number;
  fat?: number;
  carbs?: number;
  source: string;
  confidence_score?: number;
  created_at: string;
}

export interface DietLog {
  id: string;
  user_id: string;
  log_date: string;
  meal_type: string;
  plan_meal_id?: string;
  total_calories?: number;
  total_protein?: number;
  total_fat?: number;
  total_carbs?: number;
  notes?: string;
  items?: FoodItem[];
  created_at: string;
  updated_at: string;
}

export interface ParsedDietCandidate {
  food_name: string;
  name?: string;
  weight_g?: number;
  unit?: string;
  calories?: number;
  protein?: number;
  fat?: number;
  carbs?: number;
  confidence_score?: number;
  source?: string;
}

export interface ParsedDietItem extends ParsedDietCandidate {
  candidates?: ParsedDietCandidate[];
  low_confidence_candidates?: ParsedDietCandidate[];
}

export interface DailySummary {
  date: string;
  total_calories: number;
  total_protein: number;
  total_fat: number;
  total_carbs: number;
  meals_logged: string[];
  log_count: number;
}

export interface WeeklySummary {
  week_start_date: string;
  week_end_date: string;
  daily_data: Record<string, {
    calories: number;
    protein: number;
    fat: number;
    carbs: number;
    meals: string[];
  }>;
  total_calories: number;
  total_protein: number;
  total_fat: number;
  total_carbs: number;
  avg_daily_calories: number;
  today_budget?: DietBudgetSnapshot;
  emotion_exemption?: EmotionExemptionStatus | null;
}

export interface DeviationAnalysis {
  has_plan: boolean;
  message?: string;
  week_start_date?: string;
  total_plan_calories?: number;
  total_actual_calories?: number;
  total_deviation?: number;
  total_deviation_pct?: number;
  meal_deviations?: Array<{
    meal_key: string;
    plan_calories: number;
    actual_calories: number;
    calories_deviation: number;
    calories_deviation_pct: number;
  }>;
  execution_rate?: number;
}

export interface UserFoodPreference {
  id: string;
  user_id: string;
  common_foods?: Array<{ name: string; frequency?: number; avg_weight?: number }>;
  avoided_foods?: string[];
  diet_tags?: string[];
  avg_daily_calories_min?: number;
  avg_daily_calories_max?: number;
  deviation_patterns?: Array<{ meal_type: string; deviation_rate?: number }>;
  stats?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface AddMealRequest {
  plan_date: string;
  meal_type: string;
  dishes?: Dish[];
  notes?: string;
}

export interface UpdateMealRequest {
  dishes?: Dish[];
  notes?: string;
}

export interface CreateLogRequest {
  log_date: string;
  meal_type: string;
  items?: Array<{
    food_name: string;
    weight_g?: number;
    unit?: string;
    calories?: number;
    protein?: number;
    fat?: number;
    carbs?: number;
  }>;
  plan_meal_id?: string;
  notes?: string;
}

export interface UpdateLogRequest {
  log_date?: string;
  meal_type?: string;
  items?: Array<{
    food_name: string;
    weight_g?: number;
    unit?: string;
    calories?: number;
    protein?: number;
    fat?: number;
    carbs?: number;
  }>;
  notes?: string;
}

export interface LogFromTextRequest {
  text: string;
  images?: ImageData[];
  log_date?: string;
  meal_type?: string;
}

export interface RecognizeMealFromImageRequest {
  images: ImageData[];
  context_text?: string;
}

export interface RecognizeMealFromImageResponse {
  dishes: Dish[];
  message: string;
  source: string;
  confidence?: number | null;
  needs_confirmation?: boolean;
  candidates?: ParsedDietCandidate[];
}

export interface MarkMealEatenRequest {
  log_date?: string;
}

export interface UpdatePreferenceRequest {
  dietary_restrictions?: string[];
  allergies?: string[];
  favorite_cuisines?: string[];
  avoided_foods?: string[];
  disliked_foods?: string[];
  preferred_foods?: string[];
  calorie_goal?: number;
  protein_goal?: number;
  fat_goal?: number;
  carbs_goal?: number;
}

export interface DietBudgetSnapshot {
  date: string;
  base_goal?: number | null;
  today_adjustment?: number | null;
  effective_goal?: number | null;
  remaining_adjustment_cap?: number | null;
  adjustment_cap?: number | null;
  requested_delta?: number | null;
  applied_delta?: number | null;
  capped?: boolean | null;
  goal_source?: 'explicit' | 'avg7d' | 'default1800' | string | null;
  goal_seeded?: boolean | null;
  emotion_exemption?: EmotionExemptionStatus | null;
}

export interface EmotionExemptionStatus {
  active?: boolean;
  is_active?: boolean;
  date: string;
  storage?: string;
  level?: string | null;
  reason?: string | null;
  source?: string | null;
  summary?: string | null;
  activated_at?: string | null;
  delta_calories?: number | null;
  effective_goal?: number | null;
  expires_at?: string | null;
}

export interface DietReplanMealChange {
  meal_id: string;
  plan_date: string;
  meal_type: string;
  old_total_calories?: number | null;
  new_total_calories?: number | null;
  delta_calories?: number | null;
  old_note?: string | null;
  new_note?: string | null;
  new_dishes?: Dish[];
  new_totals?: {
    total_calories?: number | null;
    total_protein?: number | null;
    total_fat?: number | null;
    total_carbs?: number | null;
  };
}

export interface DietReplanPreview {
  week_start_date: string;
  affected_days: string[];
  before_summary: Record<string, unknown>;
  after_summary: Record<string, unknown>;
  meal_changes: DietReplanMealChange[];
  write_conflicts: Array<{
    meal_id?: string;
    plan_date?: string;
    meal_type?: string;
    reason: string;
  }>;
}

export interface DietReplanApplyResponse {
  action: string;
  applied_count?: number | null;
  updated_meal_ids?: string[];
  write_conflicts: Array<{
    meal_id?: string;
    plan_date?: string;
    meal_type?: string;
    reason: string;
  }>;
}

export interface ShoppingListMatchedItem {
  dish_name: string;
  matched_doc_id: string;
  ingredients: string[];
}

export interface ShoppingGroupedIngredient {
  name: string;
  count: number;
  dishes: string[];
}

export interface ShoppingListResponse {
  week_start_date: string;
  week_end_date: string;
  aggregation_basis: string;
  item_count: number;
  items: Array<{
    name: string;
    planned_count: number;
    total_weight_g?: number | null;
    meal_slots: string[];
  }>;
  matched_items: ShoppingListMatchedItem[];
  unmatched_dishes: string[];
  grouped_ingredients: ShoppingGroupedIngredient[];
}

export interface NextMealCorrectionPayload {
  plan_date: string;
  meal_type: string;
  dish_name: string;
  calories?: number | null;
  protein?: number | null;
  fat?: number | null;
  carbs?: number | null;
  nutrition_source?: string | null;
  nutrition_confidence?: number | null;
  notes?: string | null;
}

export interface NextMealCorrectionAction {
  action_id: string;
  action_kind: string;
  apply_path?: string;
  reason?: string;
  payload: NextMealCorrectionPayload;
}

export interface WeeklyNutritionSnapshot {
  title?: string;
  summary?: string;
  total_calories?: number;
  total_protein?: number;
  total_fat?: number;
  total_carbs?: number;
  deviation?: number;
  execution_rate?: number;
  [key: string]: unknown;
}

export interface WeeklySummaryBundle {
  weekly_summary: WeeklySummary;
  deviation: DeviationAnalysis;
  next_meal_correction?: NextMealCorrectionAction | null;
  nutrition_snapshot?: WeeklyNutritionSnapshot | null;
}

export interface ApplyNextMealCorrectionRequest extends NextMealCorrectionPayload {
  action_id?: string;
}

export interface ApplyNextMealCorrectionResponse {
  plan_date: string;
  meal_type: string;
  meal: DietPlanMeal;
}
