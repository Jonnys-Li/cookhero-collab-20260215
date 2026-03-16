from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Any, Optional


def build_meal_log_confirm_action(
    *,
    session_id: str,
    suggested_log_date: str,
    suggested_meal_type: str,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "action_id": f"meal-log-confirm-{uuid.uuid4().hex}",
        "action_type": "meal_log_confirm_card",
        "title": "确认记录本餐",
        "description": "点击确认后才会写入饮食管理，避免误记录。",
        "suggested_log_date": suggested_log_date,
        "suggested_meal_type": suggested_meal_type,
        "items": items,
        "source": "agent_diet_log_pipeline",
        "session_id": session_id,
    }


def infer_planmode_default_intensity(runtime: Optional[dict[str, Any]]) -> str:
    if not isinstance(runtime, dict):
        return "balanced"
    weekly_deviation = runtime.get("weekly_deviation")
    if not isinstance(weekly_deviation, dict):
        return "balanced"
    try:
        total_deviation = int(weekly_deviation.get("total_deviation"))
    except (TypeError, ValueError):
        return "balanced"
    if total_deviation >= 1200:
        return "conservative"
    if total_deviation <= 300:
        return "aggressive"
    return "balanced"


def build_meal_plan_planmode_action(
    *,
    runtime: Optional[dict[str, Any]],
    session_id: str,
) -> dict[str, Any]:
    default_intensity = infer_planmode_default_intensity(runtime)
    return {
        "action_id": f"meal-plan-planmode-{uuid.uuid4().hex}",
        "action_type": "meal_plan_planmode_card",
        "title": "先做 4 步个性化配置，再生成你的周计划",
        "description": "按步骤选择饮食与训练偏好，生成可预览、可确认写入的一周方案。",
        "timeout_seconds": 10,
        "timeout_mode": "timeout_suggest_only",
        "default_timeout_suggestion": "超时后仅保留建议，不会自动写入饮食数据。",
        "steps": [
            {
                "id": "goal_food",
                "title": "饮食目标与食物类型",
                "hint": "选择你的主要目标和偏好的食物类型。",
            },
            {
                "id": "restriction",
                "title": "限制与过敏",
                "hint": "填写需要避开的食物或过敏原。",
            },
            {
                "id": "relax",
                "title": "放松场景方式",
                "hint": "选择你更容易执行的放松方式。",
            },
            {
                "id": "weekly_intensity",
                "title": "周进度强度与训练偏好",
                "hint": "选择下周计划强度和训练偏好。",
            },
        ],
        "goal_options": [
            {"value": "fat_loss", "label": "减脂"},
            {"value": "muscle_gain", "label": "增肌"},
            {"value": "maintenance", "label": "维持体重"},
            {"value": "recovery", "label": "恢复与减压"},
        ],
        "food_type_options": [
            {"value": "chinese_home", "label": "家常中餐"},
            {"value": "high_protein", "label": "高蛋白"},
            {"value": "low_carb", "label": "低碳水"},
            {"value": "light_meal", "label": "轻食"},
            {"value": "comfort_food", "label": "安抚型食物"},
        ],
        "restriction_options": [
            {"value": "no_spicy", "label": "少辣"},
            {"value": "low_fat", "label": "低脂"},
            {"value": "vegetarian", "label": "素食优先"},
            {"value": "no_lactose", "label": "低乳糖"},
            {"value": "low_sodium", "label": "低钠"},
        ],
        "relax_mode_options": [
            {"value": "breathing", "label": "呼吸放松"},
            {"value": "walk", "label": "散步舒展"},
            {"value": "journaling", "label": "情绪记录"},
            {"value": "music", "label": "音乐放松"},
        ],
        "weekly_intensity_options": [
            {"value": "conservative", "label": "保守"},
            {"value": "balanced", "label": "平衡"},
            {"value": "aggressive", "label": "积极"},
        ],
        "training_focus_options": [
            {"value": "low_impact", "label": "低冲击"},
            {"value": "strength", "label": "力量提升"},
            {"value": "cardio", "label": "有氧耐力"},
            {"value": "mobility", "label": "灵活拉伸"},
        ],
        "defaults": {
            "goal": "fat_loss",
            "weekly_intensity": default_intensity,
            "training_focus": "low_impact",
            "cook_time_minutes": 30,
            "training_minutes_per_day": 25,
            "training_days_per_week": 3,
        },
        "source": "planmode_pipeline",
        "session_id": session_id,
    }


def infer_next_meal_plan(*, now: Optional[datetime] = None) -> tuple[date, str]:
    now = now or datetime.now()
    today = now.date()
    hour = now.hour
    if hour < 10:
        return today, "lunch"
    if hour < 15:
        return today, "dinner"
    if hour < 21:
        return today, "snack"
    return today + timedelta(days=1), "breakfast"


def should_emit_smart_recommendation_card(runtime: dict[str, Any]) -> bool:
    """
    Smart recommendation card is an *optional* UI enhancement.

    Only auto-emit it when the user's intent is likely about planning/correction,
    emotion support, or weekly progress review.
    """
    if not isinstance(runtime, dict):
        return False
    return bool(
        runtime.get("planning_triggered")
        or runtime.get("emotion_triggered")
        or runtime.get("weekly_progress_triggered")
    )


def build_smart_recommendation_action(runtime: dict[str, Any]) -> dict[str, Any]:
    plan_date, meal_type = infer_next_meal_plan()
    weekly_summary = runtime.get("weekly_summary") if isinstance(runtime, dict) else None
    weekly_deviation = (
        runtime.get("weekly_deviation") if isinstance(runtime, dict) else None
    )
    execution_rate = None
    total_deviation = None
    if isinstance(weekly_deviation, dict):
        execution_rate = weekly_deviation.get("execution_rate")
        total_deviation = weekly_deviation.get("total_deviation")
        try:
            execution_rate = float(execution_rate) if execution_rate is not None else None
        except (TypeError, ValueError):
            execution_rate = None
        try:
            total_deviation = int(total_deviation) if total_deviation is not None else None
        except (TypeError, ValueError):
            total_deviation = None

    weekly_text = "你可以说“看本周进度”获取执行摘要。"
    if execution_rate is not None and total_deviation is not None:
        weekly_text = f"本周执行率 {execution_rate:.1f}% ，总偏差 {total_deviation} kcal。"
    elif isinstance(weekly_summary, dict):
        avg_daily = weekly_summary.get("avg_daily_calories")
        if avg_daily is not None:
            weekly_text = f"本周日均摄入约 {avg_daily:.0f} kcal。"

    return {
        "action_id": f"smart-recommendation-{uuid.uuid4().hex}",
        "action_type": "smart_recommendation_card",
        "title": "我整理了一个可直接执行的智能推荐卡",
        "description": "包含下一餐纠偏、放松场景建议和周进度入口。",
        "timeout_seconds": 10,
        "timeout_mode": "timeout_suggest_only",
        "default_timeout_suggestion": "若你暂时不点击，我会保留建议，不会自动写入饮食数据。",
        "next_meal_options": [
            {
                "option_id": "balanced",
                "title": "轻负担均衡餐",
                "description": "优先蛋白 + 蔬菜，减少高油高糖负担。",
                "meal_type": meal_type,
                "plan_date": plan_date.isoformat(),
                "dish_name": "鸡蛋豆腐蔬菜碗",
                "calories": 420,
            },
            {
                "option_id": "protein",
                "title": "高蛋白稳态餐",
                "description": "帮助稳定饱腹感，避免再次冲动进食。",
                "meal_type": meal_type,
                "plan_date": plan_date.isoformat(),
                "dish_name": "鸡胸肉沙拉配酸奶",
                "calories": 460,
            },
            {
                "option_id": "comfort",
                "title": "温和安抚餐",
                "description": "低负担 + 情绪安抚，避免惩罚性节食。",
                "meal_type": meal_type,
                "plan_date": plan_date.isoformat(),
                "dish_name": "燕麦酸奶水果杯",
                "calories": 380,
            },
        ],
        "relax_suggestions": [
            "做 3 轮方块呼吸（吸4秒-停4秒-呼4秒-停4秒）。",
            "走到窗边或户外 5 分钟，放松肩颈和下颌。",
            "给自己一句中性提醒：一次波动不等于失败。",
        ],
        "weekly_progress": {
            "trigger_hint": "看本周进度",
            "summary_text": weekly_text,
            "execution_rate": execution_rate,
            "total_deviation": total_deviation,
        },
        "budget_options": [50, 100, 150],
        "source": "collaboration_pipeline",
        "session_id": runtime.get("session_id"),
    }
