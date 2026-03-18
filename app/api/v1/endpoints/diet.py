# app/api/v1/endpoints/diet.py
"""
Diet API endpoints for personal diet management.

Provides RESTful API for diet plans, meals, logs, and analysis.
"""

from __future__ import annotations

import base64
import logging
import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel, Field, field_validator

from app.diet.service import diet_service
from app.diet.database.models import MealType, DayOfWeek, DataSource
from app.diet.nutrition_snapshot import build_weekly_nutrition_snapshot

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_IMAGE_SIZE_MB = 10.0
SUPPORTED_IMAGE_FORMATS = ["image/jpeg", "image/png", "image/gif", "image/webp"]


# ==================== Request/Response Models ====================


class DishSchema(BaseModel):
    """Schema for a dish in a meal."""

    name: str = Field(..., description="菜品名称")
    weight_g: Optional[float] = Field(None, description="重量(克)")
    unit: Optional[str] = Field(None, description="单位（份/个/碗等）")
    calories: Optional[int] = Field(None, description="卡路里")
    protein: Optional[float] = Field(None, description="蛋白质(克)")
    fat: Optional[float] = Field(None, description="脂肪(克)")
    carbs: Optional[float] = Field(None, description="碳水化合物(克)")
    low_confidence_candidates: List["LowConfidenceCandidateSchema"] = Field(
        default_factory=list,
        description="低置信候选，用于前端二次确认",
    )


class AddMealRequest(BaseModel):
    """Request for adding a meal to a weekly plan."""

    plan_date: date = Field(..., description="计划日期 (YYYY-MM-DD)")
    meal_type: str = Field(..., description="餐次类型: breakfast/lunch/dinner/snack")
    dishes: Optional[List[DishSchema]] = Field(None, description="菜品列表")
    notes: Optional[str] = Field(None, description="备注")


class UpdateMealRequest(BaseModel):
    """Request for updating a meal."""

    dishes: Optional[List[DishSchema]] = None
    notes: Optional[str] = None


class CopyMealRequest(BaseModel):
    """Request for copying a meal."""

    target_date: date = Field(..., description="目标日期 (YYYY-MM-DD)")
    target_meal_type: Optional[str] = Field(None, description="目标餐次类型")


class FoodItemSchema(BaseModel):
    """Schema for a food item in a log."""

    food_name: str = Field(..., description="食物名称")
    weight_g: Optional[float] = Field(None, description="重量(克)")
    unit: Optional[str] = Field(None, description="单位")
    calories: Optional[int] = Field(None, description="卡路里")
    protein: Optional[float] = Field(None, description="蛋白质(克)")
    fat: Optional[float] = Field(None, description="脂肪(克)")
    carbs: Optional[float] = Field(None, description="碳水化合物(克)")
    source: Optional[str] = Field(None, description="数据来源")


class CreateLogRequest(BaseModel):
    """Request for creating a diet log."""

    log_date: date = Field(..., description="记录日期")
    meal_type: str = Field(..., description="餐次类型")
    items: Optional[List[FoodItemSchema]] = Field(None, description="食物列表")
    plan_meal_id: Optional[str] = Field(None, description="关联的计划餐次ID")
    notes: Optional[str] = Field(None, description="备注")


class ImageData(BaseModel):
    """Image data for multimodal diet logging."""

    data: str
    mime_type: str = "image/jpeg"

    @field_validator("mime_type")
    @classmethod
    def validate_mime_type(cls, v: str) -> str:
        if v not in SUPPORTED_IMAGE_FORMATS:
            raise ValueError(
                f"不支持的图片格式: {v}。支持的格式: {SUPPORTED_IMAGE_FORMATS}"
            )
        return v

    @field_validator("data")
    @classmethod
    def validate_data(cls, v: str) -> str:
        try:
            decoded_size = len(base64.b64decode(v))
            max_size = MAX_IMAGE_SIZE_MB * 1024 * 1024
            if decoded_size > max_size:
                raise ValueError(f"图片大小超过限制 ({MAX_IMAGE_SIZE_MB}MB)")
        except Exception as e:
            if "图片大小超过限制" in str(e):
                raise
            raise ValueError("无效的 base64 图片数据")
        return v


class LogFromTextRequest(BaseModel):
    """Request for creating a log from text description."""

    text: str = Field(..., min_length=1, max_length=1000, description="饮食描述文字")
    images: Optional[List[ImageData]] = Field(default=None, max_length=4)
    log_date: Optional[date] = Field(None, description="记录日期（默认今天）")
    meal_type: Optional[str] = Field(None, description="餐次类型（可自动推断）")


class ParseDietInputRequest(BaseModel):
    """
    Parse-only request contract (no DB writes).

    Frontend should call this endpoint first in the "photo-first" logging flow,
    then allow the user to edit items, and finally call POST /diet/logs to persist.
    """

    text: Optional[str] = Field(None, max_length=1000, description="可选饮食文字描述")
    images: Optional[List[ImageData]] = Field(default=None, max_length=4)
    log_date: Optional[date] = Field(None, description="可选记录日期（默认今天）")
    meal_type: Optional[str] = Field(None, description="可选餐次类型（可自动推断）")


class ParsedDietItemSchema(BaseModel):
    food_name: str
    weight_g: Optional[float] = None
    unit: Optional[str] = None
    calories: Optional[int] = None
    protein: Optional[float] = None
    fat: Optional[float] = None
    carbs: Optional[float] = None
    confidence_score: Optional[float] = None
    source: Optional[str] = None
    low_confidence_candidates: List["LowConfidenceCandidateSchema"] = Field(
        default_factory=list
    )


class LowConfidenceCandidateSchema(BaseModel):
    name: str
    food_name: Optional[str] = None
    weight_g: Optional[float] = None
    unit: Optional[str] = None
    calories: Optional[int] = None
    protein: Optional[float] = None
    fat: Optional[float] = None
    carbs: Optional[float] = None
    source: Optional[str] = None
    confidence_score: Optional[float] = None


class ParseDietInputResponse(BaseModel):
    meal_type: Optional[str] = None
    items: List[ParsedDietItemSchema] = Field(default_factory=list)
    used_vision: bool = False
    message: Optional[str] = None
    confidence: Optional[float] = None
    needs_confirmation: bool = False
    candidates: List[LowConfidenceCandidateSchema] = Field(default_factory=list)


class RecognizeMealFromImageRequest(BaseModel):
    """Request for recognizing meal dishes from images."""

    images: List[ImageData] = Field(..., min_length=1, max_length=4)
    context_text: Optional[str] = Field(
        None,
        max_length=1000,
        description="可选补充描述（如烹饪方式、分量）",
    )


class RecognizeMealFromImageResponse(BaseModel):
    """Response for meal recognition without side effects."""

    dishes: List[DishSchema] = Field(default_factory=list)
    message: str
    source: str = DataSource.AI_IMAGE.value
    confidence: Optional[float] = None
    needs_confirmation: bool = False
    candidates: List[LowConfidenceCandidateSchema] = Field(default_factory=list)


class UpdateLogRequest(BaseModel):
    """Request for updating a diet log."""

    log_date: Optional[date] = Field(None, description="记录日期")
    meal_type: Optional[str] = Field(None, description="餐次类型")
    items: Optional[List[FoodItemSchema]] = Field(None, description="食物列表")
    notes: Optional[str] = Field(None, description="备注")


class AddItemToLogRequest(BaseModel):
    """Request for adding an item to a log."""

    food_name: str = Field(..., description="食物名称")
    weight_g: Optional[float] = None
    unit: Optional[str] = None
    calories: Optional[int] = None
    protein: Optional[float] = None
    fat: Optional[float] = None
    carbs: Optional[float] = None
    source: Optional[str] = None


class MarkMealEatenRequest(BaseModel):
    """Request for marking a plan meal as eaten."""

    log_date: Optional[date] = Field(None, description="记录日期（默认今天）")


class UpdatePreferenceRequest(BaseModel):
    """Request for updating user preferences."""

    dietary_restrictions: Optional[List[str]] = Field(None, description="饮食限制")
    allergies: Optional[List[str]] = Field(None, description="过敏原")
    favorite_cuisines: Optional[List[str]] = Field(None, description="喜爱的菜系")
    avoided_foods: Optional[List[str]] = Field(None, description="不喜欢的食物")
    disliked_foods: Optional[List[str]] = Field(None, description="不喜欢的食物（兼容字段）")
    preferred_foods: Optional[List[str]] = Field(None, description="偏好的食物")
    calorie_goal: Optional[int] = Field(None, description="每日卡路里目标")
    protein_goal: Optional[float] = Field(None, description="每日蛋白质目标(克)")
    fat_goal: Optional[float] = Field(None, description="每日脂肪目标(克)")
    carbs_goal: Optional[float] = Field(None, description="每日碳水目标(克)")
    age: Optional[int] = Field(None, ge=12, le=100, description="年龄")
    biological_sex: Optional[str] = Field(
        None, pattern="^(male|female)$", description="生理性别"
    )
    height_cm: Optional[float] = Field(None, ge=100, le=250, description="身高(cm)")
    weight_kg: Optional[float] = Field(None, ge=20, le=350, description="体重(kg)")
    activity_level: Optional[str] = Field(
        None,
        pattern="^(sedentary|light|moderate|active|very_active)$",
        description="活动水平",
    )
    goal_intent: Optional[str] = Field(
        None,
        pattern="^(fat_loss|maintain|muscle_gain)$",
        description="当前目标方向",
    )
    use_estimated_calorie_goal: Optional[bool] = Field(
        False,
        description="是否将估算出的 TDEE 建议热量写入 calorie_goal",
    )


class ApplyNextMealCorrectionRequest(BaseModel):
    """Request for one-click next meal correction write."""

    plan_date: date = Field(..., description="计划日期 (YYYY-MM-DD)")
    meal_type: str = Field(..., description="餐次类型: breakfast/lunch/dinner/snack")
    dish_name: str = Field(..., min_length=1, max_length=80, description="菜品名称")
    calories: Optional[int] = Field(None, ge=0, description="卡路里")
    protein: Optional[float] = Field(None, ge=0, description="蛋白质(克)")
    fat: Optional[float] = Field(None, ge=0, description="脂肪(克)")
    carbs: Optional[float] = Field(None, ge=0, description="碳水(克)")
    nutrition_source: Optional[str] = Field(None, max_length=20)
    nutrition_confidence: Optional[float] = Field(None, ge=0, le=1)
    notes: Optional[str] = Field(None, max_length=200)


class ReplanCandidateSchema(BaseModel):
    dish_name: str = Field(..., min_length=1, max_length=80)
    calories: Optional[int] = Field(None, ge=0)
    protein: Optional[float] = Field(None, ge=0)
    fat: Optional[float] = Field(None, ge=0)
    carbs: Optional[float] = Field(None, ge=0)
    nutrition_source: Optional[str] = Field(None, max_length=32)
    nutrition_confidence: Optional[float] = Field(None, ge=0, le=1)
    description: Optional[str] = Field(None, max_length=200)


class ReplanPreviewRequest(BaseModel):
    target_date: date = Field(..., description="需要改餐的日期")
    meal_type: str = Field(..., description="餐次类型: breakfast/lunch/dinner/snack")
    candidate_count: int = Field(default=3, ge=1, le=3)


class ReplanPreviewResponse(BaseModel):
    target_date: Optional[str] = None
    meal_type: Optional[str] = None
    direction: Optional[str] = None
    reason: Optional[str] = None
    existing_meal: Optional[Dict[str, Any]] = None
    candidates: List[ReplanCandidateSchema] = Field(default_factory=list)
    selected_candidate: Optional[ReplanCandidateSchema] = None
    apply_path: Optional[str] = None
    weekly_context: Dict[str, Any] = Field(default_factory=dict)
    affected_days: List[str] = Field(default_factory=list)
    before_summary: Dict[str, Any] = Field(default_factory=dict)
    after_summary: Dict[str, Any] = Field(default_factory=dict)
    meal_changes: List[Dict[str, Any]] = Field(default_factory=list)
    write_conflicts: List[Dict[str, Any]] = Field(default_factory=list)
    compensation_summary: Optional[str] = None
    compensation_suggestions: List[Dict[str, Any]] = Field(default_factory=list)


class ReplanApplyRequest(BaseModel):
    target_date: Optional[date] = Field(None, description="需要改餐的日期")
    meal_type: Optional[str] = Field(None, description="餐次类型: breakfast/lunch/dinner/snack")
    selected_candidate: Optional[ReplanCandidateSchema] = None
    notes: Optional[str] = Field(None, max_length=200)
    replace_existing: bool = True
    meal_changes: List[Dict[str, Any]] = Field(default_factory=list)


class ReplanApplyResponse(BaseModel):
    action: str
    target_date: Optional[str] = None
    meal_type: Optional[str] = None
    meal: Optional[Dict[str, Any]] = None
    applied_count: Optional[int] = None
    updated_meal_ids: List[str] = Field(default_factory=list)
    write_conflicts: List[Dict[str, Any]] = Field(default_factory=list)


class EmotionExemptionStatusResponse(BaseModel):
    active: bool
    is_active: Optional[bool] = None
    date: str
    storage: str
    level: Optional[str] = None
    reason: Optional[str] = None
    source: Optional[str] = None
    summary: Optional[str] = None
    activated_at: Optional[str] = None
    delta_calories: int = 0
    effective_goal: Optional[int] = None
    expires_at: Optional[str] = None


class ShoppingListItemSchema(BaseModel):
    name: str
    planned_count: int
    total_weight_g: Optional[float] = None
    meal_slots: List[str] = Field(default_factory=list)


class ShoppingListResponse(BaseModel):
    week_start_date: str
    week_end_date: str
    aggregation_basis: str
    item_count: int
    items: List[ShoppingListItemSchema] = Field(default_factory=list)
    matched_items: List[Dict[str, Any]] = Field(default_factory=list)
    unmatched_dishes: List[str] = Field(default_factory=list)
    grouped_ingredients: List[Dict[str, Any]] = Field(default_factory=list)


class CompensationSuggestionResponse(BaseModel):
    kind: str
    title: str
    recommended_date: Optional[str] = None
    training_title: Optional[str] = None
    training_description: Optional[str] = None
    suggested_minutes: Optional[int] = None
    estimated_burn_kcal: Optional[int] = None
    relax_suggestions: List[str] = Field(default_factory=list)
    reason: str
    remaining_meal_count: int
    remaining_correction_capacity: int
    uncovered_gap: int
    goal_source: Optional[str] = None
    goal_context: Optional[Dict[str, Any]] = None


class TrendPointSchema(BaseModel):
    date: str
    value: Optional[int] = None


class GoalSourceChangeSchema(BaseModel):
    date: str
    from_: Optional[str] = Field(None, alias="from")
    to: Optional[str] = None

    model_config = {"populate_by_name": True}


class ThreeLineDailySchema(BaseModel):
    date: str
    intake_calories: int
    base_goal: Optional[int] = None
    effective_goal: Optional[int] = None
    deviation_calories: Optional[int] = None
    goal_source: Optional[str] = None
    goal_source_changed: bool = False
    emotion_exemption_active: bool = False
    emotion_exemption: Optional[Dict[str, Any]] = None


class ThreeLineSeriesSchema(BaseModel):
    intake: List[TrendPointSchema] = Field(default_factory=list)
    goal: List[TrendPointSchema] = Field(default_factory=list)
    deviation: List[TrendPointSchema] = Field(default_factory=list)


class ThreeLineTrendResponse(BaseModel):
    start_date: str
    end_date: str
    days: int
    goal_context: Optional[Dict[str, Any]] = None
    estimate_context: Optional[Dict[str, Any]] = None
    daily: List[ThreeLineDailySchema] = Field(default_factory=list)
    series: ThreeLineSeriesSchema
    goal_source_changes: List[GoalSourceChangeSchema] = Field(default_factory=list)


# ==================== Helper Functions ====================


def get_user_id(request: Request) -> str:
    """Extract user_id from request state."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="需要登录")
    return str(user_id)


def _infer_default_next_meal(target_date: date) -> tuple[date, str]:
    """
    Best-effort inference for the next meal slot.

    Diet page can pass explicit `target_date` / `meal_type`, but this keeps a
    deterministic fallback for "one-click" flows.
    """
    hour = datetime.now().hour
    if hour < 10:
        return target_date, "breakfast"
    if hour < 15:
        return target_date, "lunch"
    if hour < 20:
        return target_date, "dinner"
    return target_date, "snack"


# ==================== Plan Endpoints ====================


@router.get("/diet/plans/by-week")
async def get_plan_by_week(
    request: Request,
    week_start_date: date = Query(..., description="周开始日期（周一）"),
) -> Dict[str, Any]:
    """
    Get weekly planned meals by week start date.

    Returns the plan meals for the selected week.
    """
    user_id = get_user_id(request)
    plan = await diet_service.get_plan_by_week(user_id, week_start_date)

    if not plan:
        return {"plan": None}

    return {"plan": plan}


# ==================== Meal Endpoints ====================


@router.post("/diet/plans/meals", status_code=201)
async def add_meal(payload: AddMealRequest, request: Request) -> Dict[str, Any]:
    """
    Add a meal to a weekly plan.
    """
    user_id = get_user_id(request)

    # Convert dishes to dict format
    dishes = None
    if payload.dishes:
        dishes = [dish.model_dump() for dish in payload.dishes]

    meal = await diet_service.add_meal(
        user_id=user_id,
        plan_date=payload.plan_date,
        meal_type=payload.meal_type,
        dishes=dishes,
        notes=payload.notes,
    )

    if not meal:
        raise HTTPException(status_code=404, detail="餐次创建失败")

    return meal


@router.patch("/diet/meals/{meal_id}")
async def update_meal(
    meal_id: str, payload: UpdateMealRequest, request: Request
) -> Dict[str, Any]:
    """
    Update a meal.
    """
    user_id = get_user_id(request)

    update_data = {}
    if payload.dishes is not None:
        update_data["dishes"] = [dish.model_dump() for dish in payload.dishes]
    if payload.notes is not None:
        update_data["notes"] = payload.notes

    meal = await diet_service.update_meal(meal_id, user_id, **update_data)

    if not meal:
        raise HTTPException(status_code=404, detail="餐次不存在或无权访问")

    return meal


@router.delete("/diet/meals/{meal_id}")
async def delete_meal(meal_id: str, request: Request) -> Dict[str, str]:
    """
    Delete a meal.
    """
    user_id = get_user_id(request)

    success = await diet_service.delete_meal(meal_id, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="餐次不存在或无权访问")

    return {"message": "餐次已删除"}


@router.post("/diet/meals/{meal_id}/copy")
async def copy_meal(
    meal_id: str, payload: CopyMealRequest, request: Request
) -> Dict[str, Any]:
    """
    Copy a meal to another day/meal type.
    """
    user_id = get_user_id(request)

    meal = await diet_service.copy_meal(
        source_meal_id=meal_id,
        user_id=user_id,
        target_date=payload.target_date,
        target_meal_type=payload.target_meal_type,
    )

    if not meal:
        raise HTTPException(status_code=404, detail="餐次不存在或无权访问")

    return meal


@router.post("/diet/meals/{meal_id}/mark-eaten")
async def mark_meal_eaten(
    meal_id: str, payload: MarkMealEatenRequest, request: Request
) -> Dict[str, Any]:
    """
    Mark a planned meal as eaten.

    Creates a log entry based on the planned meal.
    """
    user_id = get_user_id(request)

    log = await diet_service.mark_plan_meal_as_eaten(
        plan_meal_id=meal_id,
        user_id=user_id,
        log_date=payload.log_date,
    )

    if not log:
        raise HTTPException(status_code=404, detail="餐次不存在或无权访问")

    return log


@router.post(
    "/diet/meals/recognize-image",
    response_model=RecognizeMealFromImageResponse,
)
async def recognize_meal_from_image(
    payload: RecognizeMealFromImageRequest,
    request: Request,
) -> RecognizeMealFromImageResponse:
    """
    Recognize meal dishes from photos and return parsed dishes only.

    This endpoint does not create or update any meal/log record.
    """
    user_id = get_user_id(request)
    images = [img.model_dump() for img in payload.images]

    try:
        result = await diet_service.recognize_meal_from_images(
            user_id=user_id,
            images=images,
            context_text=payload.context_text,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    return RecognizeMealFromImageResponse(**result)


# ==================== Log Endpoints ====================


@router.get("/diet/logs")
async def get_logs_by_date(
    request: Request,
    log_date: date = Query(..., description="查询日期"),
) -> Dict[str, Any]:
    """
    Get diet logs for a specific date.
    """
    user_id = get_user_id(request)
    logs = await diet_service.get_logs_by_date(user_id, log_date)
    return {"logs": logs, "date": log_date.isoformat()}


@router.post("/diet/logs", status_code=201)
async def create_log(payload: CreateLogRequest, request: Request) -> Dict[str, Any]:
    """
    Create a diet log entry.
    """
    user_id = get_user_id(request)

    items = None
    if payload.items:
        items = [item.model_dump() for item in payload.items]

    log = await diet_service.log_meal(
        user_id=user_id,
        log_date=payload.log_date,
        meal_type=payload.meal_type,
        items=items,
        plan_meal_id=payload.plan_meal_id,
        notes=payload.notes,
    )

    return log


@router.post("/diet/logs/from-text", status_code=201)
async def create_log_from_text(
    payload: LogFromTextRequest, request: Request
) -> Dict[str, Any]:
    """
    Create a diet log from text description.

    Uses AI to parse the text and extract food items with estimated nutrition.
    """
    user_id = get_user_id(request)

    images = None
    if payload.images:
        images = [img.model_dump() for img in payload.images]

    log = await diet_service.log_from_text(
        user_id=user_id,
        text=payload.text,
        log_date=payload.log_date,
        meal_type=payload.meal_type,
        images=images,
    )

    return log


@router.post("/diet/logs/parse", response_model=ParseDietInputResponse)
async def parse_diet_log_input(
    payload: ParseDietInputRequest,
    request: Request,
) -> ParseDietInputResponse:
    """
    Parse-only endpoint for diet logging (no DB writes).

    API Contract (recommended for frontend):
    - Request:
      {
        "text"?: string,
        "images"?: [{ "data": base64, "mime_type": "image/jpeg|png|gif|webp" }],
        "log_date"?: "YYYY-MM-DD",
        "meal_type"?: "breakfast|lunch|dinner|snack"
      }
    - Response:
      {
        "meal_type"?: string,
        "items": [{
          "food_name": string,
          "weight_g"?: number,
          "unit"?: string,
          "calories"?: number,
          "protein"?: number,
          "fat"?: number,
          "carbs"?: number,
          "confidence_score"?: number,
          "source"?: string
        }],
        "used_vision": boolean,
        "message"?: string
      }

    Notes:
    - Always returns 200 even if Vision/LLM is not configured; `items` may be empty
      and `message` will guide the user to manual editing.
    """
    user_id = get_user_id(request)

    images = None
    if payload.images:
        images = [img.model_dump() for img in payload.images]

    text = (payload.text or "").strip()
    if not text and not images:
        return ParseDietInputResponse(
            meal_type=payload.meal_type,
            items=[],
            used_vision=False,
            message="请提供文字描述或至少 1 张图片以便解析。",
        )

    try:
        parsed = await diet_service.parse_diet_input_without_side_effects(
            user_id=user_id,
            text=text,
            images=images,
        )
    except Exception:
        # Hard fallback: never 500 for parse-only.
        return ParseDietInputResponse(
            meal_type=payload.meal_type,
            items=[],
            used_vision=False,
            message="当前 AI 解析不可用，你可以手动编辑本餐记录。",
        )

    used_vision = bool(parsed.get("used_vision")) if isinstance(parsed, dict) else False
    parsed_items = parsed.get("items") if isinstance(parsed, dict) else []
    if not isinstance(parsed_items, list):
        parsed_items = []
    response_candidates = parsed.get("candidates") if isinstance(parsed, dict) else []
    if not isinstance(response_candidates, list):
        response_candidates = []

    # Fill source field so frontend can display provenance consistently.
    source = (
        DataSource.AI_IMAGE.value if used_vision else DataSource.AI_TEXT.value
    )

    out_items: list[ParsedDietItemSchema] = []
    for raw in parsed_items:
        if not isinstance(raw, dict):
            continue
        food_name = str(raw.get("food_name") or "").strip()
        if not food_name:
            continue
        out_items.append(
            ParsedDietItemSchema(
                food_name=food_name,
                weight_g=raw.get("weight_g"),
                unit=raw.get("unit"),
                calories=raw.get("calories"),
                protein=raw.get("protein"),
                fat=raw.get("fat"),
                carbs=raw.get("carbs"),
                confidence_score=raw.get("confidence_score"),
                source=str(raw.get("source") or source),
                low_confidence_candidates=[
                    LowConfidenceCandidateSchema(**candidate)
                    for candidate in (raw.get("low_confidence_candidates") or [])
                    if isinstance(candidate, dict) and candidate.get("name")
                ],
            )
        )

    meal_type = payload.meal_type or (parsed.get("meal_type") if isinstance(parsed, dict) else None)
    message = parsed.get("message") if isinstance(parsed, dict) else None
    if not out_items:
        message = "未识别到清晰食物，你可以手动编辑本餐记录。"

    return ParseDietInputResponse(
        meal_type=meal_type,
        items=out_items,
        used_vision=used_vision,
        message=message,
        confidence=parsed.get("confidence") if isinstance(parsed, dict) else None,
        needs_confirmation=bool(parsed.get("needs_confirmation")) if isinstance(parsed, dict) else False,
        candidates=[
            LowConfidenceCandidateSchema(**candidate)
            for candidate in response_candidates
            if isinstance(candidate, dict) and candidate.get("name")
        ],
    )


@router.get("/diet/logs/{log_id}")
async def get_log(log_id: str, request: Request) -> Dict[str, Any]:
    """
    Get a diet log by ID.
    """
    user_id = get_user_id(request)
    log = await diet_service.get_log(log_id)

    if not log:
        raise HTTPException(status_code=404, detail="记录不存在")

    if log.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="无权访问此记录")

    return log


@router.patch("/diet/logs/{log_id}")
async def update_log(
    log_id: str, payload: UpdateLogRequest, request: Request
) -> Dict[str, Any]:
    """
    Update a diet log.
    """
    user_id = get_user_id(request)

    items = None
    if payload.items is not None:
        items = [item.model_dump() for item in payload.items]

    log = await diet_service.update_log(
        log_id,
        user_id,
        items=items,
        meal_type=payload.meal_type,
        log_date=payload.log_date,
        notes=payload.notes,
    )

    if not log:
        raise HTTPException(status_code=404, detail="记录不存在或无权访问")

    return log


@router.delete("/diet/logs/{log_id}")
async def delete_log(log_id: str, request: Request) -> Dict[str, str]:
    """
    Delete a diet log.
    """
    user_id = get_user_id(request)

    success = await diet_service.delete_log(log_id, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="记录不存在或无权访问")

    return {"message": "记录已删除"}


@router.post("/diet/logs/{log_id}/items", status_code=201)
async def add_item_to_log(
    log_id: str, payload: AddItemToLogRequest, request: Request
) -> Dict[str, Any]:
    """
    Add a food item to an existing log.
    """
    user_id = get_user_id(request)

    item = await diet_service.add_item_to_log(
        log_id=log_id,
        user_id=user_id,
        food_name=payload.food_name,
        weight_g=payload.weight_g,
        unit=payload.unit,
        calories=payload.calories,
        protein=payload.protein,
        fat=payload.fat,
        carbs=payload.carbs,
        source=payload.source,
    )

    if not item:
        raise HTTPException(status_code=404, detail="记录不存在或无权访问")

    return item


# ==================== Analysis Endpoints ====================


@router.get(
    "/diet/emotion-exemption",
    response_model=EmotionExemptionStatusResponse,
)
async def get_emotion_exemption_status(
    request: Request,
    target_date: Optional[date] = Query(None, description="目标日期（默认今天）"),
) -> EmotionExemptionStatusResponse:
    """查询当天情绪保护期状态，Redis 不可用时自动降级。"""
    user_id = get_user_id(request)
    payload = await diet_service.get_emotion_exemption_status(user_id, target_date)
    return EmotionExemptionStatusResponse(**payload)


@router.get("/diet/budget")
async def get_budget(
    request: Request,
    target_date: Optional[date] = Query(None, description="目标日期（默认今天）"),
) -> Dict[str, Any]:
    """
    Get daily calorie budget snapshot (base goal + today's adjustment).

    This is used to provide immediate, visible feedback after emotion-support
    budget adjustments.
    """
    user_id = get_user_id(request)
    return await diet_service.get_today_budget(user_id, target_date)


@router.get("/diet/analysis/daily")
async def get_daily_summary(
    request: Request,
    target_date: date = Query(..., description="目标日期"),
) -> Dict[str, Any]:
    """
    Get daily diet summary.

    Returns nutrition totals and breakdown by meal type.
    """
    user_id = get_user_id(request)
    summary = await diet_service.get_daily_summary(user_id, target_date)
    return summary


@router.get("/diet/analysis/weekly")
async def get_weekly_summary(
    request: Request,
    week_start_date: Optional[date] = Query(None, description="周开始日期（默认本周）"),
) -> Dict[str, Any]:
    """
    Get weekly diet summary.

    Returns aggregated nutrition data for the week.
    """
    user_id = get_user_id(request)
    summary = await diet_service.get_weekly_summary(user_id, week_start_date)
    return summary


@router.get("/diet/analysis/deviation")
async def get_deviation_analysis(
    request: Request,
    week_start_date: Optional[date] = Query(None, description="周开始日期（默认本周）"),
) -> Dict[str, Any]:
    """
    Get deviation analysis between plan and actual.

    Compares planned meals with actual diet logs.
    """
    user_id = get_user_id(request)
    analysis = await diet_service.get_deviation_analysis(user_id, week_start_date)
    return analysis


@router.get(
    "/diet/analysis/compensation-suggestion",
    response_model=Optional[CompensationSuggestionResponse],
)
async def get_compensation_suggestion(
    request: Request,
    week_start_date: Optional[date] = Query(None, description="周开始日期（默认本周）"),
    target_date: Optional[date] = Query(None, description="目标日期（默认今天）"),
) -> Optional[CompensationSuggestionResponse]:
    """当剩余餐次修正空间不足时，返回训练补偿或恢复日建议。"""
    user_id = get_user_id(request)
    payload = await diet_service.get_compensation_suggestion(
        user_id=user_id,
        week_start_date=week_start_date,
        target_date=target_date,
    )
    if payload is None:
        return None
    return CompensationSuggestionResponse(**payload)


@router.get(
    "/diet/analysis/three-lines",
    response_model=ThreeLineTrendResponse,
)
async def get_three_line_trends(
    request: Request,
    days: int = Query(14, ge=7, le=14, description="查询天数，支持 7-14 天"),
    end_date: Optional[date] = Query(None, description="结束日期（默认今天）"),
) -> ThreeLineTrendResponse:
    """为趋势图提供近 7-14 天的摄入、目标、偏差及状态标记。"""
    user_id = get_user_id(request)
    payload = await diet_service.get_three_line_view(
        user_id=user_id,
        days=days,
        end_date=end_date,
    )
    return ThreeLineTrendResponse(**payload)


# ==================== Summary / Correction Endpoints ====================


@router.get(
    "/diet/replan/preview",
    response_model=ReplanPreviewResponse,
)
async def get_weekly_replan_preview(
    request: Request,
    week_start_date: Optional[date] = Query(None, description="周开始日期（默认本周）"),
) -> ReplanPreviewResponse:
    """预览未来 3-5 天的滚动重规划结果。"""
    user_id = get_user_id(request)
    preview = await diet_service.preview_weekly_replan(
        user_id=user_id,
        week_start_date=week_start_date,
    )
    return ReplanPreviewResponse(**preview)


@router.post(
    "/diet/replan/preview",
    response_model=ReplanPreviewResponse,
)
async def preview_replan(
    payload: ReplanPreviewRequest,
    request: Request,
) -> ReplanPreviewResponse:
    """兼容旧版：生成单餐次 replan 候选。"""
    user_id = get_user_id(request)
    meal_type_value = str(payload.meal_type or "").strip().lower()
    if meal_type_value not in {"breakfast", "lunch", "dinner", "snack"}:
        raise HTTPException(
            status_code=400,
            detail="meal_type 仅支持 breakfast/lunch/dinner/snack",
        )

    preview = await diet_service.preview_replan(
        user_id=user_id,
        target_date=payload.target_date,
        meal_type=meal_type_value,
        candidate_count=payload.candidate_count,
    )
    return ReplanPreviewResponse(**preview)


@router.post(
    "/diet/replan/apply",
    response_model=ReplanApplyResponse,
)
async def apply_replan(
    payload: ReplanApplyRequest,
    request: Request,
) -> ReplanApplyResponse:
    """应用滚动重规划或兼容旧版单餐次改餐。"""
    user_id = get_user_id(request)
    if payload.meal_changes:
        result = await diet_service.apply_weekly_replan(
            user_id=user_id,
            meal_changes=payload.meal_changes,
        )
        return ReplanApplyResponse(action="applied_weekly_replan", **result)

    if payload.target_date is None or payload.meal_type is None or payload.selected_candidate is None:
        raise HTTPException(status_code=400, detail="缺少 replan 应用参数")

    meal_type_value = str(payload.meal_type or "").strip().lower()
    if meal_type_value not in {"breakfast", "lunch", "dinner", "snack"}:
        raise HTTPException(
            status_code=400,
            detail="meal_type 仅支持 breakfast/lunch/dinner/snack",
        )

    result = await diet_service.apply_replan(
        user_id=user_id,
        target_date=payload.target_date,
        meal_type=meal_type_value,
        selected_candidate=payload.selected_candidate.model_dump(),
        notes=payload.notes,
        replace_existing=payload.replace_existing,
    )
    return ReplanApplyResponse(**result)


@router.get(
    "/diet/shopping-list",
    response_model=ShoppingListResponse,
)
async def get_shopping_list(
    request: Request,
    week_start_date: Optional[date] = Query(None, description="周开始日期（默认本周）"),
) -> ShoppingListResponse:
    """按计划菜品聚合一周购物清单。"""
    user_id = get_user_id(request)
    payload = await diet_service.get_shopping_list(
        user_id=user_id,
        week_start_date=week_start_date,
    )
    return ShoppingListResponse(**payload)


@router.get("/diet/summary/weekly")
async def get_weekly_summary_bundle(
    request: Request,
    week_start_date: Optional[date] = Query(None, description="周开始日期（默认本周）"),
    target_date: Optional[date] = Query(None, description="用于纠偏建议的目标日期（默认今天）"),
    meal_type: Optional[str] = Query(None, description="用于纠偏建议的餐次（可选）"),
) -> Dict[str, Any]:
    """
    Bundle endpoint for Diet page to reduce client-side stitching.

    Returns:
    - weekly_summary: /diet/analysis/weekly
    - deviation: /diet/analysis/deviation
    - next_meal_correction: a deterministic suggestion payload for one-click write
    - nutrition_snapshot: payload suitable for Community post creation
    """
    user_id = get_user_id(request)
    weekly_summary = await diet_service.get_weekly_summary(user_id, week_start_date)
    deviation = await diet_service.get_deviation_analysis(user_id, week_start_date)
    compensation_suggestion = await diet_service.get_compensation_suggestion(
        user_id=user_id,
        week_start_date=week_start_date,
        target_date=target_date,
    )

    target = target_date or date.today()
    inferred_date, inferred_meal_type = _infer_default_next_meal(target)
    meal_type_value = str(meal_type or inferred_meal_type).strip().lower()
    if meal_type_value not in {"breakfast", "lunch", "dinner", "snack"}:
        meal_type_value = inferred_meal_type

    total_dev_raw = deviation.get("total_deviation") if isinstance(deviation, dict) else None
    try:
        total_dev = int(total_dev_raw) if total_dev_raw is not None else 0
    except (TypeError, ValueError):
        total_dev = 0

    # Deterministic template suggestion: lighter if over-plan, otherwise high-protein stable meal.
    if total_dev > 0:
        suggestion = {
            "dish_name": "燕麦酸奶水果杯",
            "calories": 380,
            "protein": 16.0,
            "fat": 10.0,
            "carbs": 52.0,
            "nutrition_source": "template",
            "nutrition_confidence": 0.5,
        }
        reason = "本周摄入略高于计划，下一餐建议选择更轻量且有满足感的组合。"
    else:
        suggestion = {
            "dish_name": "鸡胸肉沙拉配酸奶",
            "calories": 460,
            "protein": 34.0,
            "fat": 16.0,
            "carbs": 32.0,
            "nutrition_source": "template",
            "nutrition_confidence": 0.5,
        }
        reason = "下一餐建议选择高蛋白稳定餐，帮助维持节奏与饱腹感。"

    emotion_exemption = (
        weekly_summary.get("emotion_exemption") if isinstance(weekly_summary, dict) else None
    )
    next_meal_correction = None
    if not (isinstance(emotion_exemption, dict) and emotion_exemption.get("active")):
        next_meal_correction = {
            "action_id": str(uuid.uuid4()),
            "action_kind": "apply_next_meal_correction",
            "apply_path": "/api/v1/diet/actions/apply-next-meal-correction",
            "reason": reason,
            "payload": {
                "plan_date": inferred_date.isoformat(),
                "meal_type": meal_type_value,
                **suggestion,
                "notes": "来自本周复盘的一键纠偏建议",
            },
        }

    return {
        "weekly_summary": weekly_summary,
        "deviation": deviation,
        "goal_context": weekly_summary.get("goal_context") if isinstance(weekly_summary, dict) else None,
        "compensation_suggestion": compensation_suggestion,
        "next_meal_correction": next_meal_correction,
        "nutrition_snapshot": build_weekly_nutrition_snapshot(
            weekly_summary=weekly_summary,
            deviation=deviation,
        ),
    }


@router.post("/diet/actions/apply-next-meal-correction", status_code=201)
async def apply_next_meal_correction(
    payload: ApplyNextMealCorrectionRequest,
    request: Request,
) -> Dict[str, Any]:
    """
    One-click write path for next meal correction.

    This endpoint is deterministic and intentionally does not call LLM/RAG.
    """
    user_id = get_user_id(request)
    meal_type_value = str(payload.meal_type or "").strip().lower()
    if meal_type_value not in {"breakfast", "lunch", "dinner", "snack"}:
        raise HTTPException(
            status_code=400, detail="meal_type 仅支持 breakfast/lunch/dinner/snack"
        )

    calories_value: Optional[int] = None
    if payload.calories is not None:
        try:
            calories_value = int(payload.calories)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="calories 必须为整数") from exc

    protein_value = payload.protein
    fat_value = payload.fat
    carbs_value = payload.carbs
    nutrition_source = payload.nutrition_source
    nutrition_confidence = payload.nutrition_confidence

    if (
        calories_value
        and calories_value > 0
        and (protein_value is None or fat_value is None or carbs_value is None)
    ):
        try:
            from app.diet.macro_estimation import (
                estimate_macros_from_calories,
                AUTO_NUTRITION_CONFIDENCE,
                AUTO_NUTRITION_SOURCE,
            )

            macros = estimate_macros_from_calories(calories_value, "maintenance")
            if protein_value is None:
                protein_value = macros.get("protein_g")
            if fat_value is None:
                fat_value = macros.get("fat_g")
            if carbs_value is None:
                carbs_value = macros.get("carbs_g")
            if not nutrition_source:
                nutrition_source = str(macros.get("source") or AUTO_NUTRITION_SOURCE)
            if nutrition_confidence is None:
                nutrition_confidence = float(
                    macros.get("confidence") or AUTO_NUTRITION_CONFIDENCE
                )
        except Exception:
            # Keep original values if macro estimation is unavailable.
            pass

    dishes = [
        {
            "name": payload.dish_name,
            "calories": calories_value,
            "protein": protein_value,
            "fat": fat_value,
            "carbs": carbs_value,
            "nutrition_source": nutrition_source or None,
            "nutrition_confidence": nutrition_confidence,
        }
    ]

    totals = diet_service._calculate_meal_totals(dishes)
    created = await diet_service.repository.add_meal_to_plan(
        user_id=str(user_id),
        plan_date=payload.plan_date,
        meal_type=meal_type_value,
        dishes=dishes,
        total_calories=totals["total_calories"],
        total_protein=totals["total_protein"],
        total_fat=totals["total_fat"],
        total_carbs=totals["total_carbs"],
        notes=payload.notes or "来自本周复盘的一键纠偏建议",
    )
    return {
        "plan_date": payload.plan_date.isoformat(),
        "meal_type": meal_type_value,
        "meal": created.to_dict(),
    }


# ==================== Preference Endpoints ====================


@router.get("/diet/preferences")
async def get_preferences(request: Request) -> Dict[str, Any]:
    """
    Get user's diet preferences.
    """
    user_id = get_user_id(request)
    pref = await diet_service.get_user_preference(user_id)

    if not pref:
        return {"message": "暂无偏好设置", "preference": None}

    return {"preference": pref}


@router.put("/diet/preferences")
async def update_preferences(
    payload: UpdatePreferenceRequest, request: Request
) -> Dict[str, Any]:
    """
    Update user's diet preferences.
    """
    user_id = get_user_id(request)

    update_data = payload.model_dump(exclude_unset=True)
    try:
        pref = await diet_service.update_user_preference(user_id, **update_data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {"preference": pref}


# ==================== Enum Info Endpoints ====================


@router.get("/diet/enums")
async def get_enums() -> Dict[str, Any]:
    """
    Get available enum values.

    Useful for frontend to populate dropdowns.
    """
    return {
        "meal_types": [{"value": t.value, "label": t.name} for t in MealType],
        "days_of_week": [{"value": d.value, "label": d.name} for d in DayOfWeek],
        "data_sources": [{"value": s.value, "label": s.name} for s in DataSource],
    }
