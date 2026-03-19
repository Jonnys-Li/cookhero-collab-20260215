# app/diet/service.py
"""
饮食模块业务服务层

提供饮食计划和记录的业务逻辑处理。
"""

import json
import logging
import re
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.diet.database.repository import diet_repository, DietRepository
from app.diet.database.models import (
    MealType,
    DataSource,
)
from app.diet.prompts import (
    DIET_LOG_IMAGE_PROMPT_TEMPLATE,
    DIET_LOG_TEXT_PROMPT_TEMPLATE,
    DIET_LOG_SYSTEM_PROMPT,
)
from app.services.emotion_exemption_service import emotion_exemption_service

logger = logging.getLogger(__name__)

GOAL_KEYS = ("calorie_goal", "protein_goal", "fat_goal", "carbs_goal")
GOALS_STATS_KEY = "goals"
GOALS_META_STATS_KEY = "goals_meta"
CALORIE_GOAL_SOURCE_KEY = "calorie_goal_source"
CALORIE_GOAL_SEEDED_KEY = "calorie_goal_seeded"
CALORIE_GOAL_SEEDED_AT_KEY = "calorie_goal_seeded_at"
METABOLIC_PROFILE_STATS_KEY = "metabolic_profile"
DEFAULT_AUTO_CALORIE_GOAL = 1800
TODAY_BUDGET_ADJUSTMENTS_KEY = "today_budget_adjustments"
TODAY_BUDGET_HISTORY_DAYS = 14
TODAY_BUDGET_DAILY_CAP = 150
EMOTION_EXEMPTION_REDIS_PREFIX = "diet:emotion_exemption"
LOW_CONFIDENCE_THRESHOLD = 0.65
LOW_CONFIDENCE_CANDIDATE_LIMIT = 3
SHOPPING_LIST_MAX_SLOTS = 8
ROLLING_REPLAN_LOOKAHEAD_DAYS = 5
ROLLING_REPLAN_TARGET_DAYS = 3
ROLLING_REPLAN_MIN_CALORIES = 220
REPLAN_AUTO_NOTE_MARKER = "[auto_replan]"
SHOPPING_SECTION_LINE_RE = re.compile(r"^(#+\s*)?(原料|食材|用料)[:：]?\s*$")
SHOPPING_BULLET_RE = re.compile(r"^[-*+]\s+")
METABOLIC_PROFILE_KEYS = (
    "age",
    "biological_sex",
    "height_cm",
    "weight_kg",
    "activity_level",
    "goal_intent",
)
ACTIVITY_LEVEL_FACTORS = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "active": 1.725,
    "very_active": 1.9,
}
GOAL_INTENT_ADJUSTMENTS = {
    "fat_loss": -450,
    "maintain": 0,
    "muscle_gain": 250,
}
PLANMODE_PROFILE_STATS_KEY = "planmode_profile"
TRAINING_FOCUS_LABEL_MAP = {
    "low_impact": "低冲击恢复训练",
    "strength": "基础力量训练",
    "cardio": "有氧耐力训练",
    "mobility": "灵活性与拉伸训练",
}
INTENSITY_LABEL_MAP = {
    "conservative": "保守",
    "balanced": "平衡",
    "aggressive": "积极",
}
RELAX_MODE_HINT_MAP = {
    "breathing": "3 轮方块呼吸（吸4秒-停4秒-呼4秒-停4秒）。",
    "walk": "餐后慢走 10 分钟，放松肩颈和下颌。",
    "journaling": "用 3 句话记录情绪触发点与可替代行动。",
    "music": "听 10 分钟舒缓音乐，避免持续刷短视频。",
}
COMPENSATION_MIN_SURPLUS_KCAL = 180
COMPENSATION_MAX_MINUTES = 45
COMPENSATION_MIN_MINUTES = 10
TRAINING_BURN_PER_MINUTE = {
    "low_impact": 4.0,
    "mobility": 3.5,
    "strength": 5.5,
    "cardio": 7.0,
}
INTENSITY_BURN_FACTOR = {
    "conservative": 0.9,
    "balanced": 1.0,
    "aggressive": 1.1,
}

REPLAN_TEMPLATE_LIBRARY: dict[str, dict[str, list[dict[str, Any]]]] = {
    "breakfast": {
        "lighter": [
            {"dish_name": "希腊酸奶水果碗", "calories": 320, "description": "更轻盈但有饱腹感"},
            {"dish_name": "燕麦豆乳杯", "calories": 300, "description": "控卡稳态早餐"},
            {"dish_name": "鸡蛋全麦三明治", "calories": 360, "description": "通勤友好型早餐"},
        ],
        "balanced": [
            {"dish_name": "鸡蛋牛油果吐司", "calories": 420, "description": "稳定输出的平衡早餐"},
            {"dish_name": "玉米鸡胸能量碗", "calories": 430, "description": "蛋白和碳水更均衡"},
            {"dish_name": "杂粮粥配水煮蛋", "calories": 390, "description": "温和、易执行"},
        ],
        "replenish": [
            {"dish_name": "鸡蛋贝果能量堡", "calories": 500, "description": "适合补充能量"},
            {"dish_name": "花生酱香蕉燕麦杯", "calories": 520, "description": "更适合偏低摄入回补"},
            {"dish_name": "牛奶麦片坚果碗", "calories": 480, "description": "高依从性补能早餐"},
        ],
    },
    "lunch": {
        "lighter": [
            {"dish_name": "鸡胸肉藜麦沙拉", "calories": 430, "description": "高蛋白轻负担午餐"},
            {"dish_name": "牛肉菌菇暖沙拉", "calories": 450, "description": "兼顾满足感与热量"},
            {"dish_name": "豆腐时蔬饭盒", "calories": 420, "description": "清爽但不空腹"},
        ],
        "balanced": [
            {"dish_name": "照烧鸡腿杂粮饭", "calories": 560, "description": "均衡、易复购"},
            {"dish_name": "番茄牛肉意面", "calories": 580, "description": "稳定执行的工作日午餐"},
            {"dish_name": "虾仁滑蛋饭", "calories": 540, "description": "恢复节奏型组合"},
        ],
        "replenish": [
            {"dish_name": "牛肉土豆能量饭", "calories": 680, "description": "适合补回偏低摄入"},
            {"dish_name": "鸡腿糙米双拼饭", "calories": 650, "description": "提高午后稳定度"},
            {"dish_name": "三文鱼牛油果饭碗", "calories": 700, "description": "补能同时保留优质脂肪"},
        ],
    },
    "dinner": {
        "lighter": [
            {"dish_name": "三文鱼蔬菜拼盘", "calories": 460, "description": "晚餐减负但保持满足感"},
            {"dish_name": "鸡丝南瓜暖碗", "calories": 420, "description": "更适合复盘后纠偏"},
            {"dish_name": "豆腐菌菇汤面", "calories": 440, "description": "温和收尾"},
        ],
        "balanced": [
            {"dish_name": "牛肉杂粮饭", "calories": 600, "description": "平衡型家常晚餐"},
            {"dish_name": "鸡腿时蔬意面", "calories": 620, "description": "兼顾恢复与饱腹"},
            {"dish_name": "虾仁豆腐盖饭", "calories": 580, "description": "稳定节奏优先"},
        ],
        "replenish": [
            {"dish_name": "牛肉土豆炖饭", "calories": 720, "description": "适合低摄入后的补足晚餐"},
            {"dish_name": "鸡腿南瓜能量盘", "calories": 700, "description": "稳步回补不暴冲"},
            {"dish_name": "三文鱼意面碗", "calories": 740, "description": "优先恢复状态"},
        ],
    },
    "snack": {
        "lighter": [
            {"dish_name": "无糖酸奶坚果杯", "calories": 220, "description": "低负担加餐"},
            {"dish_name": "苹果奶酪盒", "calories": 210, "description": "控量满足口欲"},
            {"dish_name": "豆乳水果杯", "calories": 230, "description": "更柔和的过渡加餐"},
        ],
        "balanced": [
            {"dish_name": "香蕉酸奶麦片杯", "calories": 280, "description": "平衡型加餐"},
            {"dish_name": "鸡蛋玉米小食盒", "calories": 260, "description": "延缓晚间饥饿"},
            {"dish_name": "牛奶全麦能量棒", "calories": 300, "description": "日常友好"},
        ],
        "replenish": [
            {"dish_name": "花生酱香蕉三明治", "calories": 360, "description": "适合快速回补"},
            {"dish_name": "牛奶坚果麦片杯", "calories": 340, "description": "补能但可控"},
            {"dish_name": "酸奶水果格兰诺拉", "calories": 380, "description": "高依从性补给"},
        ],
    },
}


def get_week_start_date(target_date: date) -> date:
    """获取给定日期所在周的周一日期"""
    return target_date - timedelta(days=target_date.weekday())


class DietService:
    """饮食模块业务服务"""

    def __init__(self, repository: Optional[DietRepository] = None):
        self.repository = repository or diet_repository
        self._redis = None

    def set_redis(self, redis_client: Any) -> None:
        self._redis = redis_client

    async def _build_plan_response(
        self,
        user_id: str,
        week_start_date: date,
        meals: Optional[List] = None,
    ) -> dict:
        if meals is None:
            meals = await self.repository.get_plan_meals_by_week(user_id, week_start_date)

        return {
            "user_id": user_id,
            "week_start_date": week_start_date.isoformat(),
            "meals": [meal.to_dict() for meal in meals],
        }

    @staticmethod
    def _group_items_by_log_id(items: List[dict]) -> dict:
        grouped: dict[str, List[dict]] = {}
        for item in items:
            log_id = item["log_id"]
            grouped.setdefault(log_id, []).append(item)
        return grouped

    @staticmethod
    def _build_log_dict(items: List[dict]) -> dict:
        if not items:
            return {}
        first = items[0]
        total_calories = sum(i.get("calories") or 0 for i in items)
        total_protein = sum(i.get("protein") or 0 for i in items)
        total_fat = sum(i.get("fat") or 0 for i in items)
        total_carbs = sum(i.get("carbs") or 0 for i in items)
        timestamps: List[str] = [
            str(value)
            for value in (i.get("created_at") for i in items)
            if value
        ]
        created_at = min(timestamps) if timestamps else None
        updated_at = max(timestamps) if timestamps else None
        return {
            "id": first["log_id"],
            "user_id": first["user_id"],
            "log_date": first["log_date"],
            "meal_type": first["meal_type"],
            "plan_meal_id": first.get("plan_meal_id"),
            "total_calories": total_calories or None,
            "total_protein": total_protein or None,
            "total_fat": total_fat or None,
            "total_carbs": total_carbs or None,
            "notes": first.get("notes"),
            "items": [
                {
                    key: value
                    for key, value in item.items()
                    if key not in {"user_id", "log_date", "meal_type", "notes", "plan_meal_id"}
                }
                for item in items
            ],
            "created_at": created_at,
            "updated_at": updated_at,
        }

    @staticmethod
    def _calculate_meal_totals(dishes: Optional[list]) -> dict:
        if not dishes:
            return {
                "total_calories": None,
                "total_protein": None,
                "total_fat": None,
                "total_carbs": None,
            }

        total_calories = sum((dish or {}).get("calories", 0) or 0 for dish in dishes)
        total_protein = sum((dish or {}).get("protein", 0) or 0 for dish in dishes)
        total_fat = sum((dish or {}).get("fat", 0) or 0 for dish in dishes)
        total_carbs = sum((dish or {}).get("carbs", 0) or 0 for dish in dishes)
        return {
            "total_calories": total_calories or None,
            "total_protein": total_protein or None,
            "total_fat": total_fat or None,
            "total_carbs": total_carbs or None,
        }

    @staticmethod
    def _resolve_macro_goal_from_preference(pref: Optional[object]) -> str:
        """Resolve macro goal label used by AUTO macro estimation.

        Priority:
        1) stats.planmode_profile.goal
        2) diet_tags includes any known goal label
        3) default maintenance
        """
        allowed = {"fat_loss", "muscle_gain", "maintenance", "recovery"}
        if not pref:
            return "maintenance"

        stats = getattr(pref, "stats", None)
        if isinstance(stats, dict):
            planmode_profile = stats.get("planmode_profile")
            if isinstance(planmode_profile, dict):
                goal = str(planmode_profile.get("goal") or "").strip().lower()
                if goal in allowed:
                    return goal

        diet_tags = getattr(pref, "diet_tags", None)
        if isinstance(diet_tags, list):
            for tag in diet_tags:
                text = str(tag or "").strip().lower()
                if text in allowed:
                    return text

        return "maintenance"

    async def _enrich_dishes_with_nutrition(
        self,
        *,
        user_id: str,
        dishes: Optional[list],
    ) -> tuple[list, bool]:
        if not dishes:
            return list(dishes or []), False

        enriched: list = deepcopy(list(dishes))
        changed = False

        # 1) RAG-first nutrition completion (may be unavailable in demo env)
        try:
            from app.diet.nutrition_completion_service import (
                nutrition_completion_service,
            )

            enriched, changed = await nutrition_completion_service.complete_dishes(
                user_id=user_id,
                dishes=dishes,
            )
        except Exception as exc:
            logger.warning("Nutrition completion skipped due to runtime error: %s", exc)

        # 2) AUTO macro estimation fallback: fill missing P/F/C deterministically
        try:
            from app.diet.macro_estimation import (
                estimate_macros_from_calories,
                AUTO_NUTRITION_CONFIDENCE,
                AUTO_NUTRITION_SOURCE,
            )
        except Exception:
            return list(enriched), changed

        macro_goal = "maintenance"
        try:
            pref = await self.repository.get_user_preference(user_id)
            macro_goal = self._resolve_macro_goal_from_preference(pref)
        except Exception:
            macro_goal = "maintenance"

        for dish in enriched:
            if not isinstance(dish, dict):
                continue
            calories_raw = dish.get("calories")
            try:
                calories_value = int(round(float(calories_raw))) if calories_raw is not None else 0
            except (TypeError, ValueError):
                calories_value = 0
            if calories_value <= 0:
                continue

            missing_any = any(dish.get(field) is None for field in ("protein", "fat", "carbs"))
            if not missing_any:
                continue

            macros = estimate_macros_from_calories(calories_value, macro_goal)
            updated = False

            if dish.get("protein") is None and macros.get("protein_g") is not None:
                dish["protein"] = macros["protein_g"]
                updated = True
            if dish.get("fat") is None and macros.get("fat_g") is not None:
                dish["fat"] = macros["fat_g"]
                updated = True
            if dish.get("carbs") is None and macros.get("carbs_g") is not None:
                dish["carbs"] = macros["carbs_g"]
                updated = True

            if not updated:
                continue

            # Only set source/confidence when not already present (RAG wins).
            if not dish.get("nutrition_source"):
                dish["nutrition_source"] = str(macros.get("source") or AUTO_NUTRITION_SOURCE)
            if dish.get("nutrition_confidence") is None:
                dish["nutrition_confidence"] = float(macros.get("confidence") or AUTO_NUTRITION_CONFIDENCE)

            changed = True

        return list(enriched), changed

    # ==================== 计划餐次 ====================

    async def get_plan_by_week(
        self, user_id: str, week_start_date: date
    ) -> Optional[dict]:
        """获取指定周的计划"""
        meals = await self.repository.get_plan_meals_by_week(user_id, week_start_date)
        if not meals:
            return None

        # 按需回填历史计划的营养字段，避免旧数据长期缺失 P/F/C。
        for meal in meals:
            dishes = meal.dishes if isinstance(meal.dishes, list) else []
            if not dishes:
                continue

            enriched_dishes, changed = await self._enrich_dishes_with_nutrition(
                user_id=user_id,
                dishes=dishes,
            )
            if not changed:
                continue

            totals = self._calculate_meal_totals(enriched_dishes)
            updated = await self.repository.update_meal(
                str(meal.id),
                dishes=enriched_dishes,
                total_calories=totals["total_calories"],
                total_protein=totals["total_protein"],
                total_fat=totals["total_fat"],
                total_carbs=totals["total_carbs"],
            )
            if updated:
                meal.dishes = updated.dishes
                meal.total_calories = updated.total_calories
                meal.total_protein = updated.total_protein
                meal.total_fat = updated.total_fat
                meal.total_carbs = updated.total_carbs

        return await self._build_plan_response(
            user_id=user_id,
            week_start_date=week_start_date,
            meals=meals,
        )

    # ==================== 餐次管理 ====================

    async def add_meal(
        self,
        user_id: str,
        plan_date: date,
        meal_type: str,
        dishes: Optional[list] = None,
        notes: Optional[str] = None,
    ) -> Optional[dict]:
        """添加餐次到计划"""
        normalized_dishes = dishes if isinstance(dishes, list) else None
        if normalized_dishes:
            normalized_dishes, _ = await self._enrich_dishes_with_nutrition(
                user_id=user_id,
                dishes=normalized_dishes,
            )

        totals = self._calculate_meal_totals(normalized_dishes)

        meal = await self.repository.add_meal_to_plan(
            user_id=user_id,
            plan_date=plan_date,
            meal_type=meal_type,
            dishes=normalized_dishes,
            total_calories=totals["total_calories"],
            total_protein=totals["total_protein"],
            total_fat=totals["total_fat"],
            total_carbs=totals["total_carbs"],
            notes=notes,
        )

        return meal.to_dict()

    async def update_meal(
        self,
        meal_id: str,
        user_id: str,
        **kwargs,
    ) -> Optional[dict]:
        """更新餐次"""
        # 获取餐次并验证所有权
        meal = await self.repository.get_meal(meal_id)
        if not meal:
            return None

        if meal.user_id != user_id:
            return None

        # 如果更新了 dishes，按缺失字段进行营养回填并重算总营养。
        if "dishes" in kwargs and kwargs["dishes"] is not None:
            dishes = kwargs["dishes"] if isinstance(kwargs["dishes"], list) else []
            if dishes:
                dishes, _ = await self._enrich_dishes_with_nutrition(
                    user_id=user_id,
                    dishes=dishes,
                )
            kwargs["dishes"] = dishes

            totals = self._calculate_meal_totals(dishes)
            kwargs["total_calories"] = totals["total_calories"]
            kwargs["total_protein"] = totals["total_protein"]
            kwargs["total_fat"] = totals["total_fat"]
            kwargs["total_carbs"] = totals["total_carbs"]

        updated_meal = await self.repository.update_meal(meal_id, **kwargs)
        return updated_meal.to_dict() if updated_meal else None

    async def delete_meal(self, meal_id: str, user_id: str) -> bool:
        """删除餐次"""
        # 获取餐次并验证所有权
        meal = await self.repository.get_meal(meal_id)
        if not meal:
            return False

        if meal.user_id != user_id:
            return False

        return await self.repository.delete_meal(meal_id)

    async def copy_meal(
        self,
        source_meal_id: str,
        user_id: str,
        target_date: date,
        target_meal_type: Optional[str] = None,
    ) -> Optional[dict]:
        """复制餐次到另一天"""
        # 获取源餐次并验证所有权
        meal = await self.repository.get_meal(source_meal_id)
        if not meal:
            return None

        if meal.user_id != user_id:
            return None

        new_meal = await self.repository.copy_meal(
            source_meal_id=source_meal_id,
            target_date=target_date,
            target_meal_type=target_meal_type,
        )

        return new_meal.to_dict() if new_meal else None

    # ==================== 记录管理 ====================

    async def log_meal(
        self,
        user_id: str,
        log_date: date,
        meal_type: str,
        items: Optional[List[dict]] = None,
        plan_meal_id: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> dict:
        """记录一餐饮食"""
        normalized_items = items or [
            {
                "food_name": "未记录食物",
                "source": DataSource.MANUAL.value,
            }
        ]
        created_items = await self.repository.create_log_items(
            user_id=user_id,
            log_date=log_date,
            meal_type=meal_type,
            items=normalized_items,
            notes=notes,
            plan_meal_id=plan_meal_id,
        )

        items_dict = [
            {
                **item.to_dict(),
                "user_id": item.user_id,
                "log_date": item.log_date.isoformat(),
                "meal_type": item.meal_type,
                "notes": item.notes,
                "plan_meal_id": str(item.plan_meal_id) if item.plan_meal_id else None,
            }
            for item in created_items
        ]
        return self._build_log_dict(items_dict)

    @staticmethod
    def _parse_ai_json(content: str) -> dict:
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        return json.loads(content.strip())

    @staticmethod
    def _normalize_low_confidence_candidates(raw_candidates: Any) -> List[dict]:
        if not isinstance(raw_candidates, list):
            return []

        normalized: List[dict] = []
        for raw in raw_candidates[:LOW_CONFIDENCE_CANDIDATE_LIMIT]:
            if isinstance(raw, str):
                name = raw.strip()
                if not name:
                    continue
                normalized.append({"food_name": name, "name": name})
                continue

            if not isinstance(raw, dict):
                continue

            name = str(
                raw.get("name")
                or raw.get("food_name")
                or raw.get("dish_name")
                or ""
            ).strip()
            if not name:
                continue

            candidate: dict[str, Any] = {
                "food_name": name,
                "name": name,
                "weight_g": raw.get("weight_g"),
                "unit": raw.get("unit"),
                "calories": raw.get("calories"),
                "protein": raw.get("protein"),
                "fat": raw.get("fat"),
                "carbs": raw.get("carbs"),
                "source": raw.get("source"),
            }
            confidence = raw.get("confidence_score", raw.get("confidence"))
            if isinstance(confidence, (int, float)):
                candidate["confidence_score"] = float(confidence)
            normalized.append(candidate)

        return normalized

    @classmethod
    def _normalize_parsed_items(cls, items: Any) -> List[dict]:
        if not isinstance(items, list):
            return []

        normalized: List[dict] = []
        for item in items:
            if not isinstance(item, dict):
                continue

            food_name = str(item.get("food_name") or "").strip()
            if not food_name:
                continue

            normalized.append(
                {
                    "food_name": food_name,
                    "weight_g": item.get("weight_g"),
                    "unit": item.get("unit"),
                    "calories": item.get("calories"),
                    "protein": item.get("protein"),
                    "fat": item.get("fat"),
                    "carbs": item.get("carbs"),
                    "confidence_score": item.get("confidence_score"),
                    "source": item.get("source"),
                    "low_confidence_candidates": cls._normalize_low_confidence_candidates(
                        item.get("low_confidence_candidates") or item.get("candidates")
                    ),
                    "candidates": cls._normalize_low_confidence_candidates(
                        item.get("low_confidence_candidates") or item.get("candidates")
                    ),
                }
            )
        return normalized

    @staticmethod
    def _coerce_iso_datetime(raw_value: Any) -> Optional[datetime]:
        if not isinstance(raw_value, str) or not raw_value.strip():
            return None
        try:
            parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                return parsed.astimezone(timezone.utc).replace(tzinfo=None)
            return parsed
        except ValueError:
            return None

    @staticmethod
    def _build_inactive_emotion_exemption(target_date: date, storage: str = "none") -> dict:
        return {
            "active": False,
            "date": target_date.isoformat(),
            "storage": storage,
            "reason": None,
            "source": None,
            "delta_calories": 0,
            "effective_goal": None,
            "expires_at": None,
        }

    async def _get_redis_client(self) -> Any:
        if self._redis is not None:
            return self._redis

        try:
            from app.services.auth_service import auth_service

            redis_client = getattr(auth_service, "_redis", None)
            if redis_client is not None:
                return redis_client
        except Exception:
            pass

        return None

    def _emotion_exemption_key(self, user_id: str, target_date: date) -> str:
        return f"{EMOTION_EXEMPTION_REDIS_PREFIX}:{user_id}:{target_date.isoformat()}"

    @staticmethod
    def _seconds_until_end_of_target_date(target_date: date) -> int:
        tomorrow = datetime.combine(target_date + timedelta(days=1), datetime.min.time())
        remaining = int((tomorrow - datetime.utcnow()).total_seconds())
        return max(3600, remaining)

    async def _set_emotion_exemption_state(
        self,
        *,
        user_id: str,
        target_date: date,
        delta_calories: int,
        effective_goal: Optional[int],
        reason: Optional[str],
        source: Optional[str],
    ) -> dict:
        expires_at = (
            datetime.utcnow() + timedelta(seconds=self._seconds_until_end_of_target_date(target_date))
        ).isoformat()
        payload = {
            "active": delta_calories > 0,
            "date": target_date.isoformat(),
            "storage": "redis",
            "reason": reason or "进入情绪保护期（当天更温和的执行策略）",
            "source": source or "emotion_subagent",
            "delta_calories": max(0, int(delta_calories or 0)),
            "effective_goal": effective_goal,
            "created_at": datetime.utcnow().isoformat(),
            "expires_at": expires_at,
        }

        redis_client = await self._get_redis_client()
        if redis_client is None:
            payload["storage"] = "preference_fallback"
            return payload

        try:
            await redis_client.setex(
                self._emotion_exemption_key(user_id, target_date),
                self._seconds_until_end_of_target_date(target_date),
                json.dumps(payload, ensure_ascii=False),
            )
        except Exception as exc:
            logger.warning("Failed to persist emotion exemption state: %s", exc)
            payload["storage"] = "preference_fallback"

        return payload

    def _build_emotion_exemption_from_stats(
        self,
        *,
        pref: Optional[object],
        target_date: date,
    ) -> dict:
        stats = self._normalize_stats(getattr(pref, "stats", None))
        entries = self._prune_adjustment_history(
            list(stats.get(TODAY_BUDGET_ADJUSTMENTS_KEY) or []),
            target_date,
        )
        target_key = target_date.isoformat()
        today_entries = [
            entry
            for entry in entries
            if entry.get("date") == target_key
            and "emotion" in str(entry.get("source") or "").lower()
        ]
        if not today_entries:
            return self._build_inactive_emotion_exemption(
                target_date,
                storage="preference_fallback",
            )

        latest = today_entries[-1]
        total_delta = sum(int(entry.get("delta_calories") or 0) for entry in today_entries)
        base_goal, _, _ = self._resolve_base_calorie_goal(pref)
        return {
            "active": total_delta > 0,
            "date": target_key,
            "storage": "preference_fallback",
            "reason": latest.get("reason") or "进入情绪保护期（当天更温和的执行策略）",
            "source": latest.get("source") or "emotion_subagent",
            "delta_calories": total_delta,
            "effective_goal": (
                base_goal + total_delta if isinstance(base_goal, int) else None
            ),
            "expires_at": None,
            "updated_at": latest.get("updated_at"),
        }

    async def get_emotion_exemption_status(
        self,
        user_id: str,
        target_date: Optional[date] = None,
        pref: Optional[object] = None,
    ) -> dict:
        actual_date = target_date or date.today()
        payload = await emotion_exemption_service.get_status(
            user_id=user_id,
            target_date=actual_date,
        )

        return {
            "active": bool(payload.get("is_active")),
            "is_active": bool(payload.get("is_active")),
            "date": payload.get("date") or actual_date.isoformat(),
            "storage": "redis" if payload.get("is_active") else "none",
            "level": payload.get("level"),
            "reason": payload.get("reason"),
            "source": payload.get("source"),
            "summary": payload.get("summary"),
            "activated_at": payload.get("activated_at"),
            "delta_calories": 0,
            "effective_goal": None,
            "expires_at": payload.get("expires_at"),
        }

    @staticmethod
    def _resolve_replan_direction(total_deviation: Any) -> str:
        try:
            deviation_value = int(round(float(total_deviation or 0)))
        except (TypeError, ValueError):
            deviation_value = 0
        if deviation_value > 300:
            return "lighter"
        if deviation_value < -300:
            return "replenish"
        return "balanced"

    @staticmethod
    def _build_replan_reason(direction: str, total_deviation: Any) -> str:
        try:
            deviation_value = int(round(float(total_deviation or 0)))
        except (TypeError, ValueError):
            deviation_value = 0
        if direction == "lighter":
            return f"本周累计约超出 {deviation_value} kcal，建议下一餐收一收总量。"
        if direction == "replenish":
            return f"本周累计约低于计划 {abs(deviation_value)} kcal，建议下一餐温和补回。"
        return "本周整体波动可控，下一餐以稳定执行为主。"

    def _build_replan_candidates(
        self,
        *,
        goal: str,
        meal_type: str,
        day_index: int,
        direction: str,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        try:
            from app.diet.macro_estimation import estimate_macros_from_calories
        except Exception:
            estimate_macros_from_calories = None

        templates = (
            REPLAN_TEMPLATE_LIBRARY.get(meal_type, {}).get(direction)
            or REPLAN_TEMPLATE_LIBRARY["dinner"]["balanced"]
        )
        max_candidates = max(1, min(limit, len(templates)))
        candidates: list[dict[str, Any]] = []
        for offset in range(max_candidates):
            template = templates[(day_index + offset) % len(templates)]
            calories = int(template.get("calories") or 0)
            macros = (
                estimate_macros_from_calories(calories, goal)
                if estimate_macros_from_calories
                else {}
            )
            candidates.append(
                {
                    "dish_name": str(template.get("dish_name") or "个性化推荐餐"),
                    "calories": calories or None,
                    "protein": macros.get("protein_g"),
                    "fat": macros.get("fat_g"),
                    "carbs": macros.get("carbs_g"),
                    "nutrition_source": macros.get("source") if macros else "template",
                    "nutrition_confidence": macros.get("confidence") if macros else 0.5,
                    "description": str(template.get("description") or ""),
                }
            )
        return candidates

    async def preview_replan(
        self,
        *,
        user_id: str,
        target_date: date,
        meal_type: str,
        candidate_count: int = 3,
    ) -> dict:
        week_start = get_week_start_date(target_date)
        weekly_summary = await self.get_weekly_summary(user_id, week_start)
        deviation = await self.get_deviation_analysis(user_id, week_start)
        plan_meals = await self.repository.get_plan_meals_by_week(user_id, week_start)
        current_meal = next(
            (
                meal
                for meal in plan_meals
                if meal.plan_date == target_date and meal.meal_type == meal_type
            ),
            None,
        )
        pref = await self.repository.get_user_preference(user_id)
        direction = self._resolve_replan_direction(
            deviation.get("total_deviation") if isinstance(deviation, dict) else 0
        )
        candidates = self._build_replan_candidates(
            goal=self._resolve_macro_goal_from_preference(pref),
            meal_type=meal_type,
            day_index=max(0, (target_date - week_start).days),
            direction=direction,
            limit=candidate_count,
        )
        selected_candidate = candidates[0]
        return {
            "target_date": target_date.isoformat(),
            "meal_type": meal_type,
            "direction": direction,
            "reason": self._build_replan_reason(
                direction,
                deviation.get("total_deviation") if isinstance(deviation, dict) else 0,
            ),
            "existing_meal": current_meal.to_dict() if current_meal else None,
            "candidates": candidates,
            "selected_candidate": selected_candidate,
            "apply_path": "/api/v1/diet/replan/apply",
            "weekly_context": {
                "avg_daily_calories": (
                    weekly_summary.get("avg_daily_calories")
                    if isinstance(weekly_summary, dict)
                    else None
                ),
                "base_goal": (
                    weekly_summary.get("base_goal")
                    if isinstance(weekly_summary, dict)
                    else None
                ),
                "effective_goal": (
                    weekly_summary.get("effective_goal")
                    if isinstance(weekly_summary, dict)
                    else None
                ),
                "goal_source": (
                    weekly_summary.get("goal_source")
                    if isinstance(weekly_summary, dict)
                    else None
                ),
                "estimate_context": (
                    weekly_summary.get("estimate_context")
                    if isinstance(weekly_summary, dict)
                    else None
                ),
                "weekly_goal_gap": (
                    weekly_summary.get("weekly_goal_gap")
                    if isinstance(weekly_summary, dict)
                    else None
                ),
                "goal_context": (
                    weekly_summary.get("goal_context")
                    if isinstance(weekly_summary, dict)
                    else None
                ),
                "total_deviation": (
                    deviation.get("total_deviation") if isinstance(deviation, dict) else None
                ),
                "execution_rate": (
                    deviation.get("execution_rate") if isinstance(deviation, dict) else None
                ),
            },
        }

    async def apply_replan(
        self,
        *,
        user_id: str,
        target_date: date,
        meal_type: str,
        selected_candidate: dict[str, Any],
        notes: Optional[str] = None,
        replace_existing: bool = True,
    ) -> dict:
        dish_payload = {
            "name": str(selected_candidate.get("dish_name") or "个性化推荐餐").strip(),
            "calories": selected_candidate.get("calories"),
            "protein": selected_candidate.get("protein"),
            "fat": selected_candidate.get("fat"),
            "carbs": selected_candidate.get("carbs"),
            "nutrition_source": selected_candidate.get("nutrition_source"),
            "nutrition_confidence": selected_candidate.get("nutrition_confidence"),
        }
        dishes = [dish_payload]
        totals = self._calculate_meal_totals(dishes)

        week_start = get_week_start_date(target_date)
        existing_meals = await self.repository.get_plan_meals_by_week(user_id, week_start)
        existing_meal = next(
            (
                meal
                for meal in existing_meals
                if meal.plan_date == target_date and meal.meal_type == meal_type
            ),
            None,
        )

        if replace_existing and existing_meal:
            meal = await self.repository.update_meal(
                str(existing_meal.id),
                dishes=dishes,
                total_calories=totals["total_calories"],
                total_protein=totals["total_protein"],
                total_fat=totals["total_fat"],
                total_carbs=totals["total_carbs"],
                notes=notes or "由 replan 建议更新",
            )
            action = "updated"
        else:
            meal = await self.repository.add_meal_to_plan(
                user_id=user_id,
                plan_date=target_date,
                meal_type=meal_type,
                dishes=dishes,
                total_calories=totals["total_calories"],
                total_protein=totals["total_protein"],
                total_fat=totals["total_fat"],
                total_carbs=totals["total_carbs"],
                notes=notes or "由 replan 建议创建",
            )
            action = "created"

        if not meal:
            raise RuntimeError("replan 应用失败")

        return {
            "action": action,
            "target_date": target_date.isoformat(),
            "meal_type": meal_type,
            "meal": meal.to_dict(),
        }

    @staticmethod
    def _slot_key(plan_date: date, meal_type: str) -> str:
        return f"{plan_date.isoformat()}:{meal_type}"

    @staticmethod
    def _is_replan_note(note: Optional[str]) -> bool:
        text = str(note or "").strip().lower()
        if not text:
            return False
        return REPLAN_AUTO_NOTE_MARKER in text or "由 replan" in text or "自动纠偏建议" in text

    def _build_log_slot_keys(self, logs: list[Any]) -> set[str]:
        slot_keys: set[str] = set()
        for item in logs:
            plan_date = getattr(item, "log_date", None)
            meal_type = getattr(item, "meal_type", None)
            if isinstance(plan_date, date) and isinstance(meal_type, str):
                slot_keys.add(self._slot_key(plan_date, meal_type))
        return slot_keys

    def _build_training_schedule(
        self,
        *,
        week_start: date,
        profile: Optional[dict],
    ) -> list[dict[str, Any]]:
        normalized = self._normalize_planmode_profile(profile)
        training_focus = normalized.get("training_focus") or "low_impact"
        weekly_intensity = normalized.get("weekly_intensity") or "balanced"
        training_minutes_per_day = int(normalized.get("training_minutes_per_day") or 25)
        training_days_per_week = int(normalized.get("training_days_per_week") or 0)
        training_custom = str(normalized.get("training_custom") or "").strip()

        schedule: list[dict[str, Any]] = []
        for day_index in range(7):
            target_date = week_start + timedelta(days=day_index)
            if day_index < training_days_per_week:
                title = f"{TRAINING_FOCUS_LABEL_MAP.get(training_focus, TRAINING_FOCUS_LABEL_MAP['low_impact'])} Day {day_index + 1}"
                description = (
                    f"{training_minutes_per_day} 分钟，强度档："
                    f"{INTENSITY_LABEL_MAP.get(weekly_intensity, '平衡')}"
                )
                if training_custom:
                    description = f"{description}；个性化备注：{training_custom}"
                schedule.append(
                    {
                        "date": target_date.isoformat(),
                        "kind": "training_day",
                        "title": title,
                        "description": description,
                        "training_focus": training_focus,
                        "weekly_intensity": weekly_intensity,
                        "training_minutes": training_minutes_per_day,
                    }
                )
            else:
                schedule.append(
                    {
                        "date": target_date.isoformat(),
                        "kind": "recovery_day",
                        "title": "恢复日",
                        "description": "主动恢复（散步+拉伸）",
                    }
                )
        return schedule

    def _estimate_compensation_minutes(
        self,
        *,
        uncovered_gap: int,
        training_focus: str,
        weekly_intensity: str,
    ) -> tuple[int, int]:
        burn_per_minute = TRAINING_BURN_PER_MINUTE.get(training_focus, 4.0) * INTENSITY_BURN_FACTOR.get(
            weekly_intensity,
            1.0,
        )
        raw_minutes = int(round(uncovered_gap / max(1.0, burn_per_minute) / 5.0) * 5)
        suggested_minutes = max(
            COMPENSATION_MIN_MINUTES,
            min(COMPENSATION_MAX_MINUTES, raw_minutes),
        )
        estimated_burn = int(round(suggested_minutes * burn_per_minute / 10.0) * 10)
        return suggested_minutes, max(40, estimated_burn)

    async def get_compensation_suggestion(
        self,
        *,
        user_id: str,
        week_start_date: Optional[date] = None,
        target_date: Optional[date] = None,
    ) -> Optional[dict]:
        actual_date = target_date or date.today()
        actual_week_start = week_start_date or get_week_start_date(actual_date)
        deviation = await self.get_deviation_analysis(user_id, actual_week_start)
        if not isinstance(deviation, dict) or not deviation.get("has_plan"):
            return None

        try:
            total_deviation = int(round(float(deviation.get("total_deviation") or 0)))
        except (TypeError, ValueError):
            total_deviation = 0
        if total_deviation < COMPENSATION_MIN_SURPLUS_KCAL:
            return None

        end_date = actual_week_start + timedelta(days=6)
        plan_meals = await self.repository.get_plan_meals_by_week(user_id, actual_week_start)
        logs = await self.repository.get_log_items_by_date_range(
            user_id=user_id,
            start_date=actual_week_start,
            end_date=end_date,
        )
        logged_slots = self._build_log_slot_keys(logs)
        remaining_meals = [
            meal
            for meal in plan_meals
            if meal.plan_date >= actual_date and self._slot_key(meal.plan_date, meal.meal_type) not in logged_slots
        ]
        remaining_capacity = 0
        for meal in remaining_meals:
            meal_total = meal.total_calories or self._calculate_meal_totals(meal.dishes).get("total_calories")
            if not isinstance(meal_total, (int, float)):
                continue
            remaining_capacity += max(0, int(round(float(meal_total) - ROLLING_REPLAN_MIN_CALORIES)))

        if remaining_capacity >= total_deviation:
            return None

        uncovered_gap = max(0, total_deviation - remaining_capacity)
        pref = await self.repository.get_user_preference(user_id)
        stats = self._normalize_stats(getattr(pref, "stats", None))
        planmode_profile = self._normalize_planmode_profile(self._extract_planmode_profile(stats))
        goal_context = await self.get_goal_context(user_id, actual_date)
        schedule = self._build_training_schedule(
            week_start=actual_week_start,
            profile=planmode_profile,
        )
        upcoming_training = next(
            (
                item
                for item in schedule
                if item.get("kind") == "training_day"
                and isinstance(item.get("date"), str)
                and date.fromisoformat(item["date"]) >= actual_date
            ),
            None,
        )

        base_payload = {
            "reason": (
                f"本周累计约超出 {total_deviation} kcal，剩余 {len(remaining_meals)} 餐最多还能通过改餐回收 "
                f"{remaining_capacity} kcal，单靠饮食调整空间可能不够。"
            ),
            "remaining_meal_count": len(remaining_meals),
            "remaining_correction_capacity": remaining_capacity,
            "uncovered_gap": uncovered_gap,
            "goal_source": goal_context.get("goal_source"),
            "goal_context": goal_context,
        }

        if upcoming_training:
            training_focus = str(upcoming_training.get("training_focus") or "low_impact")
            weekly_intensity = str(upcoming_training.get("weekly_intensity") or "balanced")
            suggested_minutes, estimated_burn_kcal = self._estimate_compensation_minutes(
                uncovered_gap=uncovered_gap,
                training_focus=training_focus,
                weekly_intensity=weekly_intensity,
            )
            return {
                "kind": "training_compensation",
                "title": "训练日补偿建议",
                "recommended_date": upcoming_training.get("date"),
                "training_title": upcoming_training.get("title"),
                "training_description": upcoming_training.get("description"),
                "suggested_minutes": suggested_minutes,
                "estimated_burn_kcal": estimated_burn_kcal,
                **base_payload,
            }

        relax_modes = planmode_profile.get("relax_modes") if isinstance(planmode_profile.get("relax_modes"), list) else []
        relax_suggestions = [
            RELAX_MODE_HINT_MAP[mode]
            for mode in relax_modes
            if mode in RELAX_MODE_HINT_MAP
        ] or [
            RELAX_MODE_HINT_MAP["walk"],
            RELAX_MODE_HINT_MAP["breathing"],
        ]
        recovery_day = next(
            (
                item
                for item in schedule
                if item.get("kind") == "recovery_day"
                and isinstance(item.get("date"), str)
                and date.fromisoformat(item["date"]) >= actual_date
            ),
            None,
        )
        return {
            "kind": "recovery_day",
            "title": "恢复日建议",
            "recommended_date": (recovery_day or {}).get("date") or actual_date.isoformat(),
            "training_title": (recovery_day or {}).get("title") or "恢复日",
            "training_description": (recovery_day or {}).get("description") or "主动恢复（散步+拉伸）",
            "suggested_minutes": None,
            "estimated_burn_kcal": None,
            "relax_suggestions": relax_suggestions[:3],
            **base_payload,
        }

    async def get_three_line_view(
        self,
        *,
        user_id: str,
        days: int = 14,
        end_date: Optional[date] = None,
    ) -> dict:
        actual_days = max(7, min(14, int(days or 14)))
        actual_end_date = end_date or date.today()
        start_date = actual_end_date - timedelta(days=actual_days - 1)

        budget_snapshot = await self.get_today_budget(user_id, actual_end_date)
        pref = await self.repository.get_user_preference(user_id)
        items = await self.repository.get_log_items_by_date_range(
            user_id=user_id,
            start_date=start_date,
            end_date=actual_end_date,
        )
        stats = self._normalize_stats(getattr(pref, "stats", None))
        adjustment_entries = self._prune_adjustment_history(
            list(stats.get(TODAY_BUDGET_ADJUSTMENTS_KEY) or []),
            actual_end_date,
        )

        intake_by_day: dict[str, int] = {}
        for item in items:
            day_key = item.log_date.isoformat()
            intake_by_day[day_key] = intake_by_day.get(day_key, 0) + int(round(float(item.calories or 0)))

        base_goal = budget_snapshot.get("base_goal")
        goal_source = str(budget_snapshot.get("goal_source") or "default1800")
        estimate_context = budget_snapshot.get("estimate_context")
        daily: list[dict[str, Any]] = []
        series_intake: list[dict[str, Any]] = []
        series_goal: list[dict[str, Any]] = []
        series_deviation: list[dict[str, Any]] = []
        goal_source_changes: list[dict[str, Any]] = []
        previous_goal_source: Optional[str] = None

        for offset in range(actual_days):
            current_date = start_date + timedelta(days=offset)
            date_key = current_date.isoformat()
            intake_calories = intake_by_day.get(date_key, 0)
            day_adjustment = self._sum_today_adjustment(adjustment_entries, current_date)
            effective_goal = (
                int(base_goal) + day_adjustment if isinstance(base_goal, int) else None
            )
            deviation_calories = (
                intake_calories - effective_goal if isinstance(effective_goal, int) else None
            )
            equivalent_exemption = self._build_emotion_exemption_from_stats(
                pref=pref,
                target_date=current_date,
            )
            goal_source_changed = goal_source != previous_goal_source
            if goal_source_changed:
                goal_source_changes.append(
                    {
                        "date": date_key,
                        "from": previous_goal_source,
                        "to": goal_source,
                    }
                )
            previous_goal_source = goal_source

            row = {
                "date": date_key,
                "intake_calories": intake_calories,
                "base_goal": base_goal,
                "effective_goal": effective_goal,
                "deviation_calories": deviation_calories,
                "goal_source": goal_source,
                "goal_source_changed": goal_source_changed,
                "emotion_exemption_active": bool(equivalent_exemption.get("active")),
                "emotion_exemption": equivalent_exemption,
            }
            daily.append(row)
            series_intake.append({"date": date_key, "value": intake_calories})
            series_goal.append({"date": date_key, "value": effective_goal})
            series_deviation.append({"date": date_key, "value": deviation_calories})

        return {
            "start_date": start_date.isoformat(),
            "end_date": actual_end_date.isoformat(),
            "days": actual_days,
            "goal_context": budget_snapshot.get("goal_context"),
            "estimate_context": estimate_context,
            "daily": daily,
            "series": {
                "intake": series_intake,
                "goal": series_goal,
                "deviation": series_deviation,
            },
            "goal_source_changes": goal_source_changes,
        }

    def _scale_dishes_for_replan(
        self,
        *,
        dishes: list[dict[str, Any]],
        current_calories: int,
        target_calories: int,
    ) -> list[dict[str, Any]]:
        if not dishes:
            return []

        if current_calories <= 0 or target_calories <= 0:
            return deepcopy(dishes)

        ratio = target_calories / current_calories
        scaled: list[dict[str, Any]] = []
        for dish in dishes:
            next_dish = deepcopy(dish)
            calories = dish.get("calories")
            protein = dish.get("protein")
            fat = dish.get("fat")
            carbs = dish.get("carbs")
            weight_g = dish.get("weight_g")

            if isinstance(calories, (int, float)):
                next_dish["calories"] = max(0, int(round(float(calories) * ratio)))
            if isinstance(protein, (int, float)):
                next_dish["protein"] = round(float(protein) * ratio, 1)
            if isinstance(fat, (int, float)):
                next_dish["fat"] = round(float(fat) * ratio, 1)
            if isinstance(carbs, (int, float)):
                next_dish["carbs"] = round(float(carbs) * ratio, 1)
            if isinstance(weight_g, (int, float)):
                next_dish["weight_g"] = round(float(weight_g) * ratio, 1)
            scaled.append(next_dish)
        return scaled

    def _build_rolling_replan_note(self, *, reason: str, original_note: Optional[str]) -> str:
        base = f"{REPLAN_AUTO_NOTE_MARKER} {reason}"
        note = str(original_note or "").strip()
        if note and note != base and not self._is_replan_note(note):
            return f"{base} | 原备注：{note}"
        return base

    def _build_write_conflict(
        self,
        *,
        meal: Any,
        reason: str,
    ) -> dict[str, Any]:
        return {
            "meal_id": str(getattr(meal, "id", "")),
            "plan_date": getattr(meal, "plan_date").isoformat(),
            "meal_type": getattr(meal, "meal_type"),
            "reason": reason,
        }

    def _build_training_compensation_suggestions(
        self,
        *,
        deviation_value: int,
        remaining_shift: int,
        meal_changes: list[dict[str, Any]],
        write_conflicts: list[dict[str, Any]],
    ) -> tuple[Optional[str], list[dict[str, Any]]]:
        if deviation_value <= 450:
            return None, []

        unresolved_kcal = abs(remaining_shift) if remaining_shift < 0 else 0
        if meal_changes and unresolved_kcal < 180:
            return None, []
        if not meal_changes and not write_conflicts:
            return None, []

        target_kcal = unresolved_kcal or deviation_value
        if target_kcal >= 550:
            suggestions = [
                {
                    "title": "轻快步行",
                    "minutes": 40,
                    "estimated_kcal_burn": 170,
                    "intensity": "low_impact",
                    "reason": "放在饭后或晚间完成，帮助回收一部分多余热量，同时不打乱恢复节奏。",
                },
                {
                    "title": "低冲击单车 / 椭圆机",
                    "minutes": 30,
                    "estimated_kcal_burn": 180,
                    "intensity": "moderate",
                    "reason": "优先中低强度有氧，不需要一次性补完整周偏差。",
                },
            ]
        elif target_kcal >= 320:
            suggestions = [
                {
                    "title": "晚饭后快走",
                    "minutes": 30,
                    "estimated_kcal_burn": 130,
                    "intensity": "low_impact",
                    "reason": "优先稳态活动，帮助消化并降低补偿性节食的冲动。",
                },
                {
                    "title": "短时循环训练",
                    "minutes": 20,
                    "estimated_kcal_burn": 110,
                    "intensity": "moderate",
                    "reason": "选择自重深蹲、划船机或台阶等可控动作，以舒适强度为主。",
                },
            ]
        else:
            suggestions = [
                {
                    "title": "饭后散步",
                    "minutes": 20,
                    "estimated_kcal_burn": 80,
                    "intensity": "low_impact",
                    "reason": "把注意力放在回到节奏，而不是惩罚式补偿。",
                },
                {
                    "title": "拉伸 + 核心激活",
                    "minutes": 15,
                    "estimated_kcal_burn": 50,
                    "intensity": "mobility",
                    "reason": "适合饮食修正空间有限时作为低压力补充，不建议叠加高强度训练。",
                },
            ]

        if meal_changes:
            summary = (
                f"未来餐次最多只能平滑吸收约 {target_kcal} kcal，"
                "可在本周补 1-2 次轻量运动帮助回到节奏，不建议用极端节食或高强度惩罚式训练。"
            )
        else:
            summary = (
                f"未来餐次已基本没有安全调整空间，本周仍有约 {target_kcal} kcal 需要温和处理；"
                "建议优先选择低冲击活动，而不是再压低进食。"
            )

        return summary, suggestions

    async def _build_weekly_budget_timeline(
        self,
        *,
        user_id: str,
        week_start_date: date,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for offset in range(7):
            target_date = week_start_date + timedelta(days=offset)
            budget = await self.get_today_budget(user_id, target_date)
            rows.append(
                {
                    "date": target_date.isoformat(),
                    "base_goal": budget.get("base_goal"),
                    "effective_goal": budget.get("effective_goal"),
                    "goal_source": budget.get("goal_source"),
                    "goal_seeded": budget.get("goal_seeded"),
                    "emotion_exemption": budget.get("emotion_exemption"),
                }
            )
        return rows

    async def preview_weekly_replan(
        self,
        *,
        user_id: str,
        week_start_date: Optional[date] = None,
        lookahead_days: int = ROLLING_REPLAN_LOOKAHEAD_DAYS,
    ) -> dict:
        actual_week_start = week_start_date or get_week_start_date(date.today())
        weekly_summary = await self.get_weekly_summary(user_id, actual_week_start)
        deviation = await self.get_deviation_analysis(user_id, actual_week_start)
        plan_meals = await self.repository.get_plan_meals_by_week(user_id, actual_week_start)
        end_date = actual_week_start + timedelta(days=6)
        start_date = max(date.today(), actual_week_start)
        preview_end = min(end_date, start_date + timedelta(days=max(1, lookahead_days) - 1))

        logs = await self.repository.get_log_items_by_date_range(
            user_id=user_id,
            start_date=actual_week_start,
            end_date=end_date,
        )
        log_slot_keys = self._build_log_slot_keys(logs)

        future_meals = [
            meal
            for meal in sorted(plan_meals, key=lambda m: (m.plan_date, m.meal_type))
            if start_date <= meal.plan_date <= preview_end
        ]

        eligible_meals: list[Any] = []
        write_conflicts: list[dict[str, Any]] = []
        affected_day_keys: list[str] = []

        for meal in future_meals:
            slot_key = self._slot_key(meal.plan_date, meal.meal_type)
            if slot_key in log_slot_keys:
                write_conflicts.append(
                    self._build_write_conflict(meal=meal, reason="已有实际记录，跳过重规划")
                )
                continue

            if meal.notes and not self._is_replan_note(meal.notes):
                write_conflicts.append(
                    self._build_write_conflict(meal=meal, reason="检测到人工备注，视为手动调整")
                )
                continue

            meal_total = meal.total_calories or self._calculate_meal_totals(meal.dishes).get(
                "total_calories"
            )
            if not isinstance(meal_total, (int, float)) or meal_total <= 0:
                write_conflicts.append(
                    self._build_write_conflict(meal=meal, reason="餐次缺少可调整的热量信息")
                )
                continue

            eligible_meals.append(meal)
            day_key = meal.plan_date.isoformat()
            if day_key not in affected_day_keys:
                affected_day_keys.append(day_key)

        deviation_value = int(round(float(deviation.get("total_deviation") or 0)))
        requested_shift = -deviation_value
        remaining_shift = requested_shift
        meal_changes: list[dict[str, Any]] = []

        for index, meal in enumerate(eligible_meals):
            meal_total = int(
                round(
                    float(
                        meal.total_calories
                        or self._calculate_meal_totals(meal.dishes).get("total_calories")
                        or 0
                    )
                )
            )
            remaining_count = max(1, len(eligible_meals) - index)
            proposed_shift = int(round(remaining_shift / remaining_count))
            next_total = max(ROLLING_REPLAN_MIN_CALORIES, meal_total + proposed_shift)
            actual_shift = next_total - meal_total
            remaining_shift -= actual_shift

            updated_dishes = self._scale_dishes_for_replan(
                dishes=list(meal.dishes or []),
                current_calories=meal_total,
                target_calories=next_total,
            )
            updated_totals = self._calculate_meal_totals(updated_dishes)
            reason = self._build_replan_reason(
                self._resolve_replan_direction(deviation_value),
                deviation_value,
            )
            meal_changes.append(
                {
                    "meal_id": str(meal.id),
                    "plan_date": meal.plan_date.isoformat(),
                    "meal_type": meal.meal_type,
                    "old_total_calories": meal_total,
                    "new_total_calories": updated_totals.get("total_calories") or next_total,
                    "delta_calories": actual_shift,
                    "old_note": meal.notes,
                    "new_note": self._build_rolling_replan_note(
                        reason=reason,
                        original_note=meal.notes,
                    ),
                    "new_dishes": updated_dishes,
                    "new_totals": updated_totals,
                }
            )

        before_total = sum(
            int(round(float(change.get("old_total_calories") or 0))) for change in meal_changes
        )
        after_total = sum(
            int(round(float(change.get("new_total_calories") or 0))) for change in meal_changes
        )
        compensation_summary, compensation_suggestions = (
            self._build_training_compensation_suggestions(
                deviation_value=deviation_value,
                remaining_shift=remaining_shift,
                meal_changes=meal_changes,
                write_conflicts=write_conflicts,
            )
        )

        return {
            "week_start_date": actual_week_start.isoformat(),
            "affected_days": affected_day_keys,
            "before_summary": {
                "future_meal_count": len(meal_changes),
                "total_future_calories": before_total,
                "total_deviation": deviation_value,
                "weekly_goal_gap": (
                    weekly_summary.get("weekly_goal_gap")
                    if isinstance(weekly_summary, dict)
                    else None
                ),
            },
            "after_summary": {
                "future_meal_count": len(meal_changes),
                "projected_future_calories": after_total,
                "applied_shift": after_total - before_total,
                "remaining_unapplied_shift": remaining_shift,
            },
            "weekly_context": {
                "goal_context": (
                    weekly_summary.get("goal_context")
                    if isinstance(weekly_summary, dict)
                    else None
                ),
                "estimate_context": (
                    weekly_summary.get("estimate_context")
                    if isinstance(weekly_summary, dict)
                    else None
                ),
                "goal_source": (
                    weekly_summary.get("goal_source")
                    if isinstance(weekly_summary, dict)
                    else None
                ),
                "base_goal": (
                    weekly_summary.get("base_goal")
                    if isinstance(weekly_summary, dict)
                    else None
                ),
            },
            "meal_changes": meal_changes,
            "write_conflicts": write_conflicts,
            "compensation_summary": compensation_summary,
            "compensation_suggestions": compensation_suggestions,
        }

    async def apply_weekly_replan(
        self,
        *,
        user_id: str,
        meal_changes: list[dict[str, Any]],
    ) -> dict:
        write_conflicts: list[dict[str, Any]] = []
        applied_meal_ids: list[str] = []

        for change in meal_changes:
            meal_id = str(change.get("meal_id") or "").strip()
            if not meal_id:
                continue
            meal = await self.repository.get_meal(meal_id)
            if not meal or meal.user_id != user_id:
                write_conflicts.append(
                    {
                        "meal_id": meal_id,
                        "plan_date": change.get("plan_date"),
                        "meal_type": change.get("meal_type"),
                        "reason": "餐次不存在或无权访问",
                    }
                )
                continue

            slot_logs = await self.repository.get_log_items_by_date(
                user_id=user_id,
                log_date=meal.plan_date,
            )
            if any(str(item.meal_type) == str(meal.meal_type) for item in slot_logs):
                write_conflicts.append(
                    self._build_write_conflict(meal=meal, reason="已有实际记录，未覆盖")
                )
                continue

            expected_total = change.get("old_total_calories")
            if (
                isinstance(expected_total, (int, float))
                and isinstance(meal.total_calories, (int, float))
                and int(round(float(expected_total))) != int(round(float(meal.total_calories)))
            ):
                write_conflicts.append(
                    self._build_write_conflict(meal=meal, reason="餐次热量已变化，请刷新预览")
                )
                continue

            if meal.notes and not self._is_replan_note(meal.notes):
                write_conflicts.append(
                    self._build_write_conflict(meal=meal, reason="检测到人工备注，未覆盖")
                )
                continue

            updated_dishes = change.get("new_dishes") if isinstance(change.get("new_dishes"), list) else []
            updated_totals = change.get("new_totals") if isinstance(change.get("new_totals"), dict) else {}
            updated_meal = await self.repository.update_meal(
                meal_id,
                dishes=updated_dishes,
                total_calories=updated_totals.get("total_calories"),
                total_protein=updated_totals.get("total_protein"),
                total_fat=updated_totals.get("total_fat"),
                total_carbs=updated_totals.get("total_carbs"),
                notes=change.get("new_note") or self._build_rolling_replan_note(
                    reason="来自滚动重规划",
                    original_note=meal.notes,
                ),
            )
            if updated_meal:
                applied_meal_ids.append(str(updated_meal.id))

        return {
            "applied_count": len(applied_meal_ids),
            "updated_meal_ids": applied_meal_ids,
            "write_conflicts": write_conflicts,
        }

    @staticmethod
    def _normalize_ingredient_name(raw_value: str) -> str:
        text = str(raw_value or "").strip()
        if not text:
            return ""
        text = SHOPPING_BULLET_RE.sub("", text).strip()
        text = re.split(r"\s{2,}|\t+", text)[0]
        text = re.split(r"(?<!\d)[0-9]+", text)[0]
        text = text.replace("适量", "").replace("少许", "").strip(" ：:-")
        return text.strip()

    def _extract_ingredients_from_content(self, content: str) -> list[str]:
        if not isinstance(content, str) or not content.strip():
            return []
        lines = [line.rstrip() for line in content.splitlines()]
        ingredients: list[str] = []
        in_section = False
        for line in lines:
            stripped = line.strip()
            if not stripped:
                if in_section and ingredients:
                    break
                continue
            if SHOPPING_SECTION_LINE_RE.match(stripped):
                in_section = True
                continue
            if in_section:
                if stripped.startswith("#"):
                    break
                normalized = self._normalize_ingredient_name(stripped)
                if normalized:
                    ingredients.append(normalized)
        return ingredients

    async def get_shopping_list(
        self,
        *,
        user_id: str,
        week_start_date: Optional[date] = None,
    ) -> dict:
        actual_week_start = week_start_date or get_week_start_date(date.today())
        meals = await self.repository.get_plan_meals_by_week(user_id, actual_week_start)
        aggregated: Dict[str, dict[str, Any]] = {}
        dish_names: list[str] = []

        for meal in meals:
            dishes = meal.dishes if isinstance(meal.dishes, list) else []
            for dish in dishes:
                if not isinstance(dish, dict):
                    continue
                name = str(dish.get("name") or "").strip()
                if not name:
                    continue
                dish_names.append(name)
                normalized_key = name.lower()
                slot = f"{meal.plan_date.isoformat()}:{meal.meal_type}"
                entry = aggregated.setdefault(
                    normalized_key,
                    {
                        "name": name,
                        "planned_count": 0,
                        "total_weight_g": 0.0,
                        "meal_slots": [],
                    },
                )
                entry["planned_count"] += 1
                weight = dish.get("weight_g")
                if isinstance(weight, (int, float)):
                    entry["total_weight_g"] += float(weight)
                if slot not in entry["meal_slots"] and len(entry["meal_slots"]) < SHOPPING_LIST_MAX_SLOTS:
                    entry["meal_slots"].append(slot)

        items = sorted(
            (
                {
                    **value,
                    "total_weight_g": (
                        round(value["total_weight_g"], 1) if value["total_weight_g"] > 0 else None
                    ),
                }
                for value in aggregated.values()
            ),
            key=lambda item: (-item["planned_count"], item["name"]),
        )

        matched_items: list[dict[str, Any]] = []
        unmatched_dishes: list[str] = []
        grouped_index: dict[str, dict[str, Any]] = {}

        if dish_names:
            try:
                from sqlalchemy import or_, select

                from app.database.models import KnowledgeDocumentModel
                from app.database.session import get_session_context

                async with get_session_context() as session:
                    stmt = (
                        select(KnowledgeDocumentModel)
                        .where(KnowledgeDocumentModel.dish_name.in_(list(set(dish_names))))
                        .order_by(KnowledgeDocumentModel.updated_at.desc())
                    )
                    docs = list((await session.execute(stmt)).scalars().all())
                docs_by_name: dict[str, Any] = {}
                for doc in docs:
                    docs_by_name.setdefault(str(doc.dish_name).strip().lower(), doc)
            except Exception as exc:
                logger.warning("Failed to build shopping-list doc matches: %s", exc)
                docs_by_name = {}

            for raw_name in dish_names:
                normalized_name = raw_name.strip().lower()
                doc = docs_by_name.get(normalized_name)
                if not doc:
                    unmatched_dishes.append(raw_name)
                    continue

                ingredients = self._extract_ingredients_from_content(str(doc.content or ""))
                matched_items.append(
                    {
                        "dish_name": raw_name,
                        "matched_doc_id": str(doc.id),
                        "ingredients": ingredients,
                    }
                )

                for ingredient in ingredients:
                    grouped = grouped_index.setdefault(
                        ingredient,
                        {
                            "name": ingredient,
                            "count": 0,
                            "dishes": [],
                        },
                    )
                    grouped["count"] += 1
                    if raw_name not in grouped["dishes"]:
                        grouped["dishes"].append(raw_name)

        return {
            "week_start_date": actual_week_start.isoformat(),
            "week_end_date": (actual_week_start + timedelta(days=6)).isoformat(),
            "aggregation_basis": "planned_dishes",
            "item_count": len(items),
            "items": items,
            "matched_items": matched_items,
            "unmatched_dishes": sorted(set(unmatched_dishes)),
            "grouped_ingredients": sorted(
                grouped_index.values(),
                key=lambda item: (-item["count"], item["name"]),
            ),
        }

    async def _parse_diet_input_with_ai(
        self,
        user_id: str,
        text: str = "",
        images: Optional[list] = None,
    ) -> dict:
        from app.config import settings
        from app.llm.provider import LLMProvider

        provider = LLMProvider(settings.llm)
        invoker = provider.create_invoker(llm_type="fast")

        parsed = None
        used_vision = False

        if images:
            try:
                from app.vision.provider import vision_provider, ImageInput

                if vision_provider.is_enabled:
                    image_inputs = [
                        ImageInput.from_base64(
                            img.get("data", ""),
                            img.get("mime_type") or "image/jpeg",
                        )
                        for img in images
                        if img.get("data")
                    ]
                    if image_inputs:
                        extra_text = f"，以及用户补充描述：{text}" if text else ""
                        vision_prompt = DIET_LOG_IMAGE_PROMPT_TEMPLATE.format(
                            extra_text=extra_text
                        )
                        response = await vision_provider.analyze(
                            text=vision_prompt,
                            images=image_inputs,
                            user_id=user_id,
                            conversation_id=None,
                        )
                        parsed = self._parse_ai_json(str(response))
                        used_vision = True
            except Exception as exc:
                logger.warning("Failed to parse diet images: %s", exc)

        if parsed is None and text.strip():
            prompt = DIET_LOG_TEXT_PROMPT_TEMPLATE.format(text=text)
            response = await invoker.ainvoke(
                [
                    {"role": "system", "content": DIET_LOG_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ]
            )
            parsed = self._parse_ai_json(str(response.content))

        if not isinstance(parsed, dict):
            return {
                "meal_type": None,
                "items": [],
                "used_vision": used_vision,
            }

        return {
            "meal_type": parsed.get("meal_type"),
            "items": self._normalize_parsed_items(parsed.get("items", [])),
            "used_vision": used_vision,
            "message": parsed.get("message"),
        }

    async def parse_diet_input(
        self,
        user_id: str,
        text: str = "",
        images: Optional[list] = None,
    ) -> dict:
        """Parse diet input into structured items without side effects.

        This method is intentionally "parse-only" and does not write any diet logs.
        It is used by Agent UI flows to show a confirmation card before persisting.

        Returns:
            {"meal_type": Optional[str], "items": List[dict], "used_vision": bool}
        """
        try:
            parsed = await self._parse_diet_input_with_ai(
                user_id=user_id,
                text=text,
                images=images,
            )
        except Exception as exc:
            logger.warning("Failed to parse diet input (parse-only): %s", exc)
            return {
                "meal_type": None,
                "items": [],
                "used_vision": False,
            }

        if not isinstance(parsed, dict):
            return {
                "meal_type": None,
                "items": [],
                "used_vision": False,
            }

        items = parsed.get("items")
        if not isinstance(items, list):
            items = []

        return {
            "meal_type": parsed.get("meal_type"),
            "items": self._normalize_parsed_items(items),
            "used_vision": bool(parsed.get("used_vision")),
            "message": parsed.get("message"),
            "confidence": parsed.get("confidence"),
            "needs_confirmation": bool(parsed.get("needs_confirmation")),
            "candidates": self._normalize_low_confidence_candidates(
                parsed.get("candidates")
            ),
        }

    async def parse_diet_input_without_side_effects(
        self,
        user_id: str,
        text: str = "",
        images: Optional[list] = None,
    ) -> dict:
        """
        Backward/UX-friendly alias for parse-only flows.

        The Diet "photo-first" flow calls this method from a dedicated parse-only
        endpoint. It must never write any diet logs/meals.
        """
        return await self.parse_diet_input(
            user_id=user_id,
            text=text,
            images=images,
        )

    async def recognize_meal_from_images(
        self,
        user_id: str,
        images: list,
        context_text: Optional[str] = None,
    ) -> dict:
        from app.vision.provider import vision_provider

        if not vision_provider.is_enabled:
            raise RuntimeError(
                "当前未开启拍照识别，请先配置 VISION_API_KEY 或可用的 LLM_API_KEY"
            )

        try:
            parsed = await self._parse_diet_input_with_ai(
                user_id=user_id,
                text=context_text or "",
                images=images,
            )
        except Exception as exc:
            logger.error("Failed to recognize meal from images: %s", exc)
            return {
                "dishes": [],
                "message": "AI 识别失败，请手动补充菜品信息",
                "source": DataSource.AI_IMAGE.value,
            }

        dishes = []
        for item in parsed.get("items", []):
            dish_name = str(item.get("food_name") or "").strip()
            if not dish_name:
                continue
            candidates = self._normalize_low_confidence_candidates(
                item.get("low_confidence_candidates") or item.get("candidates")
            )
            dishes.append(
                {
                    "name": dish_name,
                    "weight_g": item.get("weight_g"),
                    "unit": item.get("unit"),
                    "calories": item.get("calories"),
                    "protein": item.get("protein"),
                    "fat": item.get("fat"),
                    "carbs": item.get("carbs"),
                    "confidence_score": item.get("confidence_score"),
                    "candidates": candidates,
                    "low_confidence_candidates": candidates,
                }
            )

        if not dishes:
            return {
                "dishes": [],
                "message": "未识别到清晰食物，请手动补充",
                "source": DataSource.AI_IMAGE.value,
                "needs_confirmation": False,
                "confidence": None,
                "candidates": [],
            }

        confidence_values = [
            float(item.get("confidence_score"))
            for item in parsed.get("items", [])
            if isinstance(item, dict) and isinstance(item.get("confidence_score"), (int, float))
        ]
        confidence = min(confidence_values) if confidence_values else None
        needs_confirmation = bool(
            isinstance(confidence, float) and confidence < LOW_CONFIDENCE_THRESHOLD
        )
        top_candidates: list[dict[str, Any]] = []
        for dish in dishes:
            for candidate in dish.get("candidates") or []:
                if candidate in top_candidates:
                    continue
                top_candidates.append(candidate)
                if len(top_candidates) >= LOW_CONFIDENCE_CANDIDATE_LIMIT:
                    break
            if len(top_candidates) >= LOW_CONFIDENCE_CANDIDATE_LIMIT:
                break

        return {
            "dishes": dishes,
            "message": (
                "识别存在低置信候选，请确认后再保存"
                if needs_confirmation
                else "识别完成"
            ),
            "source": DataSource.AI_IMAGE.value,
            "confidence": confidence,
            "needs_confirmation": needs_confirmation,
            "candidates": top_candidates,
        }

    async def log_from_text(
        self,
        user_id: str,
        text: str,
        log_date: Optional[date] = None,
        meal_type: Optional[str] = None,
        images: Optional[list] = None,
    ) -> dict:
        """从文字或图片描述记录饮食（AI 解析）

        示例输入：
        - "今天中午吃了牛肉面和一个苹果"
        - "早餐：两个鸡蛋、一杯牛奶"
        """
        try:
            parsed_result = await self._parse_diet_input_with_ai(
                user_id=user_id,
                text=text,
                images=images,
            )
            actual_meal_type = (
                meal_type
                or parsed_result.get("meal_type")
                or MealType.SNACK.value
            )
            items = parsed_result.get("items", [])
            used_vision = bool(parsed_result.get("used_vision"))

            # 标记来源为 AI 解析
            for item in items:
                item["source"] = (
                    DataSource.AI_IMAGE.value if used_vision else DataSource.AI_TEXT.value
                )

            return await self.log_meal(
                user_id=user_id,
                log_date=log_date or date.today(),
                meal_type=actual_meal_type,
                items=items,
            )

        except Exception as e:
            logger.error(f"Failed to parse diet text: {e}")
            # 降级处理：创建简单记录
            return await self.log_meal(
                user_id=user_id,
                log_date=log_date or date.today(),
                meal_type=meal_type or MealType.SNACK.value,
                items=[
                    {
                        "food_name": text[:100],  # 使用原始文本作为名称
                        "source": DataSource.AI_TEXT.value,
                    }
                ],
                notes=f"AI 解析失败，原始描述：{text}",
            )

    async def mark_plan_meal_as_eaten(
        self,
        plan_meal_id: str,
        user_id: str,
        log_date: Optional[date] = None,
    ) -> Optional[dict]:
        """将计划中的餐次标记为已吃"""
        # 获取计划餐次
        meal = await self.repository.get_meal(plan_meal_id)
        if not meal:
            return None

        if meal.user_id != user_id:
            return None

        # 确定日期
        actual_date = log_date or date.today()

        # 从计划餐次创建记录
        items = []
        if meal.dishes:
            for dish in meal.dishes:
                items.append(
                    {
                        "food_name": dish.get("name", "Unknown"),
                        "weight_g": dish.get("weight_g"),
                        "unit": dish.get("unit"),
                        "calories": dish.get("calories"),
                        "protein": dish.get("protein"),
                        "fat": dish.get("fat"),
                        "carbs": dish.get("carbs"),
                        "source": DataSource.MANUAL.value,
                    }
                )

        return await self.log_meal(
            user_id=user_id,
            log_date=actual_date,
            meal_type=meal.meal_type,
            items=items,
            plan_meal_id=plan_meal_id,
        )

    async def get_log(self, log_id: str) -> Optional[dict]:
        """获取记录详情"""
        items = await self.repository.get_log_items_by_log_id(log_id)
        if not items:
            return None
        items_dict = [
            {
                **item.to_dict(),
                "user_id": item.user_id,
                "log_date": item.log_date.isoformat(),
                "meal_type": item.meal_type,
                "notes": item.notes,
                "plan_meal_id": str(item.plan_meal_id) if item.plan_meal_id else None,
            }
            for item in items
        ]
        return self._build_log_dict(items_dict)

    async def get_logs_by_date(self, user_id: str, log_date: date) -> List[dict]:
        """获取某天的所有记录"""
        items = await self.repository.get_log_items_by_date(user_id, log_date)
        items_dict = [
            {
                **item.to_dict(),
                "user_id": item.user_id,
                "log_date": item.log_date.isoformat(),
                "meal_type": item.meal_type,
                "notes": item.notes,
                "plan_meal_id": str(item.plan_meal_id) if item.plan_meal_id else None,
            }
            for item in items
        ]
        grouped = self._group_items_by_log_id(items_dict)
        logs = [self._build_log_dict(group) for group in grouped.values()]
        return sorted(logs, key=lambda log: (log.get("meal_type"), log.get("log_date")))

    async def update_log(
        self,
        log_id: str,
        user_id: str,
        items: Optional[List[dict]] = None,
        meal_type: Optional[str] = None,
        log_date: Optional[date] = None,
        notes: Optional[str] = None,
    ) -> Optional[dict]:
        """更新记录"""
        existing_items = await self.repository.get_log_items_by_log_id(log_id)
        if not existing_items or existing_items[0].user_id != user_id:
            return None

        existing = existing_items[0]
        actual_log_date = log_date or existing.log_date
        actual_meal_type = meal_type or existing.meal_type
        actual_notes = notes if notes is not None else existing.notes
        plan_meal_id = str(existing.plan_meal_id) if existing.plan_meal_id else None

        if items is not None:
            await self.repository.delete_log_items(log_id)
            await self.repository.create_log_items(
                user_id=user_id,
                log_date=actual_log_date,
                meal_type=actual_meal_type,
                items=items,
                notes=actual_notes,
                plan_meal_id=plan_meal_id,
                log_id=existing.log_id,
            )
        else:
            await self.repository.update_log_metadata(
                log_id,
                meal_type=meal_type,
                log_date=log_date,
                notes=notes,
            )

        return await self.get_log(log_id)

    async def delete_log(self, log_id: str, user_id: str) -> bool:
        """删除记录"""
        items = await self.repository.get_log_items_by_log_id(log_id)
        if not items or items[0].user_id != user_id:
            return False

        return await self.repository.delete_log_items(log_id)

    async def add_item_to_log(
        self,
        log_id: str,
        user_id: str,
        food_name: str,
        **kwargs,
    ) -> Optional[dict]:
        """添加食品项到记录"""
        items = await self.repository.get_log_items_by_log_id(log_id)
        if not items or items[0].user_id != user_id:
            return None

        item = await self.repository.add_item_to_log(
            log_id=log_id,
            food_name=food_name,
            **kwargs,
        )
        return item.to_dict() if item else None

    # ==================== 分析统计 ====================

    async def get_daily_summary(self, user_id: str, target_date: date) -> dict:
        """获取某天的饮食摘要"""
        return await self.repository.get_daily_summary(user_id, target_date)

    async def get_weekly_summary(
        self, user_id: str, week_start_date: Optional[date] = None
    ) -> dict:
        """获取某周的饮食摘要"""
        if not week_start_date:
            week_start_date = get_week_start_date(date.today())
        summary = await self.repository.get_weekly_summary(user_id, week_start_date)
        if not isinstance(summary, dict):
            return {}

        context_date = (
            date.today()
            if week_start_date <= date.today() <= week_start_date + timedelta(days=6)
            else week_start_date
        )
        budget = await self.get_today_budget(user_id, context_date)
        summary["today_budget"] = budget
        summary["emotion_exemption"] = budget.get("emotion_exemption")
        summary["goal_context"] = budget.get("goal_context")
        summary["goal_source"] = budget.get("goal_source")
        summary["base_goal"] = budget.get("base_goal")
        summary["effective_goal"] = budget.get("effective_goal")
        summary["estimate_context"] = budget.get("estimate_context")
        summary["daily_budget_timeline"] = await self._build_weekly_budget_timeline(
            user_id=user_id,
            week_start_date=week_start_date,
        )
        base_goal = budget.get("base_goal")
        if isinstance(base_goal, int):
            weekly_goal_calories = int(base_goal) * 7
            try:
                total_calories = int(round(float(summary.get("total_calories") or 0)))
            except (TypeError, ValueError):
                total_calories = 0
            try:
                avg_daily_calories = float(summary.get("avg_daily_calories") or 0)
            except (TypeError, ValueError):
                avg_daily_calories = 0.0
            summary["weekly_goal_calories"] = weekly_goal_calories
            summary["weekly_goal_gap"] = total_calories - weekly_goal_calories
            summary["avg_daily_goal_gap"] = round(avg_daily_calories - float(base_goal), 1)
        return summary

    async def get_deviation_analysis(
        self, user_id: str, week_start_date: Optional[date] = None
    ) -> dict:
        """获取计划与实际的偏差分析"""
        if not week_start_date:
            week_start_date = get_week_start_date(date.today())
        return await self.repository.calculate_plan_vs_actual_deviation(
            user_id, week_start_date
        )

    # ==================== 用户偏好 ====================

    def _normalize_stats(self, stats: Optional[dict]) -> dict:
        """标准化 stats 字段，保证返回可写字典。"""
        if not isinstance(stats, dict):
            return {}
        return deepcopy(stats)

    def _merge_stats(self, base: Optional[dict], patch: Optional[dict]) -> dict:
        """浅层合并 stats 字段（dict 值按一层键合并）。"""
        merged = self._normalize_stats(base)
        if not isinstance(patch, dict):
            return merged

        for key, value in patch.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                next_value = dict(merged[key])
                next_value.update(value)
                merged[key] = next_value
            else:
                merged[key] = value
        return merged

    def _extract_goals(self, stats: Optional[dict]) -> dict:
        if not isinstance(stats, dict):
            return {}
        goals = stats.get(GOALS_STATS_KEY)
        return goals if isinstance(goals, dict) else {}

    def _extract_goals_meta(self, stats: Optional[dict]) -> dict:
        if not isinstance(stats, dict):
            return {}
        goals_meta = stats.get(GOALS_META_STATS_KEY)
        return goals_meta if isinstance(goals_meta, dict) else {}

    def _extract_metabolic_profile(self, stats: Optional[dict]) -> dict:
        if not isinstance(stats, dict):
            return {}
        profile = stats.get(METABOLIC_PROFILE_STATS_KEY)
        return profile if isinstance(profile, dict) else {}

    def _extract_planmode_profile(self, stats: Optional[dict]) -> dict:
        if not isinstance(stats, dict):
            return {}
        profile = stats.get(PLANMODE_PROFILE_STATS_KEY)
        return profile if isinstance(profile, dict) else {}

    def _normalize_planmode_profile(self, profile: Optional[dict]) -> dict:
        if not isinstance(profile, dict):
            return {}

        weekly_intensity = str(profile.get("weekly_intensity") or "balanced").strip().lower()
        if weekly_intensity not in INTENSITY_LABEL_MAP:
            weekly_intensity = "balanced"

        training_focus = str(profile.get("training_focus") or "low_impact").strip().lower()
        if training_focus not in TRAINING_FOCUS_LABEL_MAP:
            training_focus = "low_impact"

        relax_modes = profile.get("relax_modes") if isinstance(profile.get("relax_modes"), list) else []
        normalized_relax_modes = [
            str(mode).strip().lower()
            for mode in relax_modes
            if str(mode).strip().lower() in RELAX_MODE_HINT_MAP
        ]

        return {
            "goal": str(profile.get("goal") or "maintenance").strip().lower(),
            "weekly_intensity": weekly_intensity,
            "training_focus": training_focus,
            "training_minutes_per_day": max(10, min(120, int(profile.get("training_minutes_per_day") or 25))),
            "training_days_per_week": max(0, min(7, int(profile.get("training_days_per_week") or 0))),
            "training_custom": str(profile.get("training_custom") or "").strip(),
            "relax_modes": normalized_relax_modes,
        }

    def _normalize_metabolic_profile(self, profile: Optional[dict]) -> dict:
        if not isinstance(profile, dict):
            return {}

        normalized: dict[str, Any] = {}

        age = profile.get("age")
        if isinstance(age, (int, float)) and 12 <= int(age) <= 100:
            normalized["age"] = int(age)

        biological_sex = str(profile.get("biological_sex") or "").strip().lower()
        if biological_sex in {"male", "female"}:
            normalized["biological_sex"] = biological_sex

        height_cm = profile.get("height_cm")
        if isinstance(height_cm, (int, float)) and 100 <= float(height_cm) <= 250:
            normalized["height_cm"] = round(float(height_cm), 1)

        weight_kg = profile.get("weight_kg")
        if isinstance(weight_kg, (int, float)) and 20 <= float(weight_kg) <= 350:
            normalized["weight_kg"] = round(float(weight_kg), 1)

        activity_level = str(profile.get("activity_level") or "").strip().lower()
        if activity_level in ACTIVITY_LEVEL_FACTORS:
            normalized["activity_level"] = activity_level

        goal_intent = str(profile.get("goal_intent") or "").strip().lower()
        if goal_intent in GOAL_INTENT_ADJUSTMENTS:
            normalized["goal_intent"] = goal_intent

        return normalized

    @staticmethod
    def _round_calorie_value(value: float) -> int:
        return int(round(value / 10.0) * 10)

    def _build_metabolic_estimate(self, profile: Optional[dict]) -> Optional[dict]:
        normalized = self._normalize_metabolic_profile(profile)
        required_keys = {
            "age",
            "biological_sex",
            "height_cm",
            "weight_kg",
            "activity_level",
            "goal_intent",
        }
        if not required_keys.issubset(normalized.keys()):
            return None

        weight_kg = float(normalized["weight_kg"])
        height_cm = float(normalized["height_cm"])
        age = int(normalized["age"])
        sex_bias = 5 if normalized["biological_sex"] == "male" else -161
        bmr_raw = 10 * weight_kg + 6.25 * height_cm - 5 * age + sex_bias
        activity_factor = ACTIVITY_LEVEL_FACTORS[normalized["activity_level"]]
        tdee_raw = bmr_raw * activity_factor
        goal_adjustment = GOAL_INTENT_ADJUSTMENTS[normalized["goal_intent"]]
        recommended_goal = max(1200, self._round_calorie_value(tdee_raw + goal_adjustment))

        return {
            "formula": "mifflin_st_jeor",
            "bmr_kcal": self._round_calorie_value(bmr_raw),
            "tdee_kcal": self._round_calorie_value(tdee_raw),
            "activity_factor": activity_factor,
            "goal_adjustment_kcal": goal_adjustment,
            "recommended_calorie_goal": recommended_goal,
            "goal_intent": normalized["goal_intent"],
            "is_complete": True,
        }

    def _serialize_preference(self, pref: Optional[object]) -> Optional[dict]:
        if not pref:
            return None

        payload = pref.to_dict()
        stats = self._normalize_stats(getattr(pref, "stats", None))
        metabolic_profile = self._normalize_metabolic_profile(
            self._extract_metabolic_profile(stats)
        )
        payload["metabolic_profile"] = metabolic_profile or None
        payload["metabolic_estimate"] = self._build_metabolic_estimate(metabolic_profile)
        return payload

    def _extract_metabolic_estimate_from_pref(self, pref: Optional[object]) -> Optional[dict]:
        if not pref:
            return None
        stats = self._normalize_stats(getattr(pref, "stats", None))
        metabolic_profile = self._normalize_metabolic_profile(
            self._extract_metabolic_profile(stats)
        )
        return self._build_metabolic_estimate(metabolic_profile)

    def _build_goal_context(
        self,
        pref: Optional[object],
        target_date: date,
        *,
        today_adjustment: int = 0,
        base_goal_override: Optional[int] = None,
        effective_goal_override: Optional[int] = None,
        goal_source_override: Optional[str] = None,
        goal_seeded_override: Optional[bool] = None,
    ) -> dict[str, Any]:
        base_goal, goal_source, goal_seeded = self._resolve_base_calorie_goal(pref)
        if isinstance(base_goal_override, int):
            base_goal = base_goal_override
        if goal_source_override is not None:
            goal_source = goal_source_override
        if goal_seeded_override is not None:
            goal_seeded = goal_seeded_override

        effective_goal = effective_goal_override
        if effective_goal is None and isinstance(base_goal, int):
            effective_goal = base_goal + max(0, int(today_adjustment or 0))

        estimate = self._extract_metabolic_estimate_from_pref(pref)
        estimate_context = None
        if isinstance(estimate, dict):
            estimate_context = {
                "source": "metabolic_profile",
                "formula": estimate.get("formula"),
                "bmr_kcal": estimate.get("bmr_kcal"),
                "tdee_kcal": estimate.get("tdee_kcal"),
                "recommended_calorie_goal": estimate.get("recommended_calorie_goal"),
                "goal_intent": estimate.get("goal_intent"),
                "activity_factor": estimate.get("activity_factor"),
                "is_complete": bool(estimate.get("is_complete")),
            }

        return {
            "date": target_date.isoformat(),
            "base_goal": base_goal,
            "effective_goal": effective_goal,
            "goal_source": goal_source,
            "goal_seeded": goal_seeded,
            "estimate_context": estimate_context,
            "uses_tdee_estimate": goal_source == "tdee_estimate",
            "fallback_used": goal_source in {"avg7d", "default1800"},
        }

    async def get_goal_context(
        self,
        user_id: str,
        target_date: Optional[date] = None,
    ) -> dict[str, Any]:
        actual_date = target_date or date.today()
        pref = await self.repository.get_user_preference(user_id)
        pref, base_goal, goal_source, goal_seeded = await self._ensure_base_calorie_goal(
            user_id=user_id,
            pref=pref,
            target_date=actual_date,
        )
        if pref or isinstance(base_goal, int):
            return self._build_goal_context(
                pref,
                actual_date,
                base_goal_override=base_goal,
                effective_goal_override=base_goal,
                goal_source_override=goal_source,
                goal_seeded_override=goal_seeded,
            )
        return {
            "date": actual_date.isoformat(),
            "base_goal": DEFAULT_AUTO_CALORIE_GOAL,
            "effective_goal": DEFAULT_AUTO_CALORIE_GOAL,
            "goal_source": "default1800",
            "goal_seeded": True,
            "estimate_context": None,
            "uses_tdee_estimate": False,
            "fallback_used": True,
        }

    def _resolve_base_calorie_goal(
        self,
        pref: Optional[object],
    ) -> tuple[Optional[int], Optional[str], bool]:
        if not pref:
            return None, None, False

        stats = getattr(pref, "stats", None)
        goals = self._extract_goals(stats)
        goals_meta = self._extract_goals_meta(stats)
        goal_value = goals.get("calorie_goal")
        if isinstance(goal_value, (int, float)):
            source = str(goals_meta.get(CALORIE_GOAL_SOURCE_KEY) or "").strip()
            if source not in {"explicit", "avg7d", "default1800", "tdee_estimate"}:
                source = "explicit"
            seeded_value = goals_meta.get(CALORIE_GOAL_SEEDED_KEY)
            seeded = bool(seeded_value) if seeded_value is not None else source != "explicit"
            return int(goal_value), source, seeded

        estimate = self._extract_metabolic_estimate_from_pref(pref)
        recommended_goal = estimate.get("recommended_calorie_goal") if isinstance(estimate, dict) else None
        if isinstance(recommended_goal, int):
            return int(recommended_goal), "tdee_estimate", False

        avg_min = getattr(pref, "avg_daily_calories_min", None)
        avg_max = getattr(pref, "avg_daily_calories_max", None)
        if isinstance(avg_min, int) and isinstance(avg_max, int):
            return int((avg_min + avg_max) / 2), "explicit", False
        if isinstance(avg_max, int):
            return avg_max, "explicit", False
        if isinstance(avg_min, int):
            return avg_min, "explicit", False
        return None, None, False

    async def _resolve_recent_calorie_avg(
        self,
        user_id: str,
        target_date: date,
    ) -> Optional[int]:
        start_date = target_date - timedelta(days=6)
        items = await self.repository.get_log_items_by_date_range(
            user_id=user_id,
            start_date=start_date,
            end_date=target_date,
        )

        if not items:
            return None

        daily_totals: dict[str, float] = {}
        for item in items:
            day_key = item.log_date.isoformat()
            daily_totals[day_key] = daily_totals.get(day_key, 0.0) + float(
                item.calories or 0
            )

        non_zero_days = [value for value in daily_totals.values() if value > 0]
        if not non_zero_days:
            return None
        return int(round(sum(non_zero_days) / len(non_zero_days)))

    async def _ensure_base_calorie_goal(
        self,
        *,
        user_id: str,
        pref: Optional[object],
        target_date: date,
    ) -> tuple[Optional[object], Optional[int], Optional[str], bool]:
        current_goal, source, seeded = self._resolve_base_calorie_goal(pref)
        if isinstance(current_goal, int):
            return pref, current_goal, source or "explicit", seeded

        avg_goal = await self._resolve_recent_calorie_avg(user_id, target_date)
        if isinstance(avg_goal, int):
            resolved_goal = avg_goal
            resolved_source = "avg7d"
        else:
            resolved_goal = DEFAULT_AUTO_CALORIE_GOAL
            resolved_source = "default1800"

        stats = self._normalize_stats(getattr(pref, "stats", None))
        goals = self._extract_goals(stats)
        goals["calorie_goal"] = int(resolved_goal)
        stats[GOALS_STATS_KEY] = goals

        goals_meta = self._extract_goals_meta(stats)
        goals_meta[CALORIE_GOAL_SOURCE_KEY] = resolved_source
        goals_meta[CALORIE_GOAL_SEEDED_KEY] = True
        goals_meta[CALORIE_GOAL_SEEDED_AT_KEY] = datetime.utcnow().isoformat()
        stats[GOALS_META_STATS_KEY] = goals_meta

        next_pref = await self.repository.upsert_user_preference(user_id, stats=stats)
        return next_pref, int(resolved_goal), resolved_source, True

    def _prune_adjustment_history(self, entries: list, target_date: date) -> list[dict]:
        min_date = target_date - timedelta(days=TODAY_BUDGET_HISTORY_DAYS - 1)
        normalized: list[dict] = []

        for entry in entries:
            if not isinstance(entry, dict):
                continue
            date_str = entry.get("date")
            if not isinstance(date_str, str):
                continue
            try:
                entry_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                continue
            if entry_date < min_date:
                continue

            delta = entry.get("delta_calories", 0)
            try:
                delta_value = int(delta)
            except (TypeError, ValueError):
                delta_value = 0

            normalized.append(
                {
                    "date": entry_date.isoformat(),
                    "delta_calories": max(0, delta_value),
                    "reason": str(entry.get("reason") or ""),
                    "source": str(entry.get("source") or "emotion_subagent"),
                    "updated_at": str(entry.get("updated_at") or ""),
                }
            )

        return normalized

    def _sum_today_adjustment(self, entries: list[dict], target_date: date) -> int:
        target_key = target_date.isoformat()
        return sum(
            int(item.get("delta_calories") or 0)
            for item in entries
            if item.get("date") == target_key
        )

    def _build_budget_snapshot(
        self,
        pref: Optional[object],
        target_date: date,
    ) -> dict:
        stats = self._normalize_stats(getattr(pref, "stats", None))
        entries = self._prune_adjustment_history(
            list(stats.get(TODAY_BUDGET_ADJUSTMENTS_KEY) or []),
            target_date,
        )
        today_adjustment = self._sum_today_adjustment(entries, target_date)
        base_goal, goal_source, goal_seeded = self._resolve_base_calorie_goal(pref)
        effective_goal = (
            base_goal + today_adjustment if isinstance(base_goal, int) else None
        )
        goal_context = self._build_goal_context(
            pref,
            target_date,
            today_adjustment=today_adjustment,
            base_goal_override=base_goal,
            effective_goal_override=effective_goal,
            goal_source_override=goal_source,
            goal_seeded_override=goal_seeded,
        )

        return {
            "date": target_date.isoformat(),
            "base_goal": base_goal,
            "today_adjustment": today_adjustment,
            "effective_goal": effective_goal,
            "remaining_adjustment_cap": max(0, TODAY_BUDGET_DAILY_CAP - today_adjustment),
            "adjustment_cap": TODAY_BUDGET_DAILY_CAP,
            "goal_source": goal_source,
            "goal_seeded": goal_seeded,
            "goal_context": goal_context,
            "estimate_context": goal_context.get("estimate_context"),
        }

    async def get_user_preference(self, user_id: str) -> Optional[dict]:
        """获取用户偏好"""
        pref = await self.repository.get_user_preference(user_id)
        return self._serialize_preference(pref)

    async def get_today_budget(
        self,
        user_id: str,
        target_date: Optional[date] = None,
    ) -> dict:
        """获取用户当天热量预算与临时调整状态。"""
        actual_date = target_date or date.today()
        pref = await self.repository.get_user_preference(user_id)
        pref, _, _, _ = await self._ensure_base_calorie_goal(
            user_id=user_id,
            pref=pref,
            target_date=actual_date,
        )

        if not pref:
            fallback_goal = DEFAULT_AUTO_CALORIE_GOAL
            goal_context = {
                "date": actual_date.isoformat(),
                "base_goal": fallback_goal,
                "effective_goal": fallback_goal,
                "goal_source": "default1800",
                "goal_seeded": True,
                "estimate_context": None,
                "uses_tdee_estimate": False,
                "fallback_used": True,
            }
            snapshot = {
                "date": actual_date.isoformat(),
                "base_goal": fallback_goal,
                "today_adjustment": 0,
                "effective_goal": fallback_goal,
                "remaining_adjustment_cap": TODAY_BUDGET_DAILY_CAP,
                "adjustment_cap": TODAY_BUDGET_DAILY_CAP,
                "goal_source": "default1800",
                "goal_seeded": True,
                "goal_context": goal_context,
                "estimate_context": None,
            }
            snapshot["emotion_exemption"] = await self.get_emotion_exemption_status(
                user_id=user_id,
                target_date=actual_date,
                pref=None,
            )
            return snapshot

        stats = self._normalize_stats(pref.stats)
        cleaned_entries = self._prune_adjustment_history(
            list(stats.get(TODAY_BUDGET_ADJUSTMENTS_KEY) or []),
            actual_date,
        )
        if cleaned_entries != list(stats.get(TODAY_BUDGET_ADJUSTMENTS_KEY) or []):
            stats[TODAY_BUDGET_ADJUSTMENTS_KEY] = cleaned_entries
            pref = await self.repository.upsert_user_preference(user_id, stats=stats)

        snapshot = self._build_budget_snapshot(pref, actual_date)
        snapshot["emotion_exemption"] = await self.get_emotion_exemption_status(
            user_id=user_id,
            target_date=actual_date,
            pref=pref,
        )
        return snapshot

    async def adjust_today_budget(
        self,
        user_id: str,
        delta_calories: int,
        reason: Optional[str] = None,
        target_date: Optional[date] = None,
        source: str = "emotion_subagent",
    ) -> dict:
        """
        增加当天临时热量预算。

        仅允许正值，且单日累计上限为 TODAY_BUDGET_DAILY_CAP。
        """
        try:
            requested_delta = int(delta_calories)
        except (TypeError, ValueError) as exc:
            raise ValueError("delta_calories 必须是正整数") from exc

        if requested_delta <= 0:
            raise ValueError("delta_calories 必须大于 0")

        actual_date = target_date or date.today()
        pref = await self.repository.get_user_preference(user_id)
        pref, _, _, _ = await self._ensure_base_calorie_goal(
            user_id=user_id,
            pref=pref,
            target_date=actual_date,
        )
        stats = self._normalize_stats(pref.stats if pref else None)

        entries = self._prune_adjustment_history(
            list(stats.get(TODAY_BUDGET_ADJUSTMENTS_KEY) or []),
            actual_date,
        )
        current_total = self._sum_today_adjustment(entries, actual_date)
        remaining = max(0, TODAY_BUDGET_DAILY_CAP - current_total)
        applied_delta = min(requested_delta, remaining)

        if applied_delta > 0:
            entries.append(
                {
                    "date": actual_date.isoformat(),
                    "delta_calories": applied_delta,
                    "reason": reason or "情绪支持临时调整",
                    "source": source or "emotion_subagent",
                    "updated_at": datetime.utcnow().isoformat(),
                }
            )

        stats[TODAY_BUDGET_ADJUSTMENTS_KEY] = entries
        pref = await self.repository.upsert_user_preference(user_id, stats=stats)

        snapshot = self._build_budget_snapshot(pref, actual_date)
        emotion_exemption = await self.get_emotion_exemption_status(
            user_id=user_id,
            target_date=actual_date,
            pref=pref,
        )
        snapshot.update(
            {
                "requested_delta": requested_delta,
                "applied_delta": applied_delta,
                "capped": applied_delta < requested_delta,
                "emotion_exemption": emotion_exemption,
            }
        )
        return snapshot

    async def update_user_preference(self, user_id: str, **kwargs) -> dict:
        """更新用户偏好"""
        update_data = dict(kwargs)
        if "disliked_foods" in update_data and "avoided_foods" not in update_data:
            update_data["avoided_foods"] = update_data.pop("disliked_foods")
        else:
            update_data.pop("disliked_foods", None)

        use_estimated_calorie_goal = bool(
            update_data.pop("use_estimated_calorie_goal", False)
        )

        goal_updates = {}
        for key in GOAL_KEYS:
            if key in update_data:
                value = update_data.pop(key)
                if value is not None:
                    goal_updates[key] = value

        metabolic_profile_updates = {}
        for key in METABOLIC_PROFILE_KEYS:
            if key in update_data:
                value = update_data.pop(key)
                if value is not None:
                    metabolic_profile_updates[key] = value

        existing_pref = await self.repository.get_user_preference(user_id)
        stats_patch = update_data.pop("stats", None)
        merged_stats = self._merge_stats(
            getattr(existing_pref, "stats", None),
            stats_patch,
        )
        existing_metabolic_profile = self._normalize_metabolic_profile(
            self._extract_metabolic_profile(merged_stats)
        )
        if metabolic_profile_updates:
            existing_metabolic_profile.update(
                self._normalize_metabolic_profile(metabolic_profile_updates)
            )
            merged_stats[METABOLIC_PROFILE_STATS_KEY] = existing_metabolic_profile

        estimated_calorie_goal: Optional[int] = None
        if use_estimated_calorie_goal:
            estimate = self._build_metabolic_estimate(existing_metabolic_profile)
            if not estimate:
                raise ValueError("代谢画像未填写完整，无法根据 BMR/TDEE 自动估算热量目标")
            estimated_calorie_goal = int(estimate["recommended_calorie_goal"])

        if goal_updates:
            goals = self._extract_goals(merged_stats)
            goals.update(goal_updates)
            merged_stats[GOALS_STATS_KEY] = goals
            if "calorie_goal" in goal_updates:
                goals_meta = self._extract_goals_meta(merged_stats)
                goals_meta[CALORIE_GOAL_SOURCE_KEY] = "explicit"
                goals_meta[CALORIE_GOAL_SEEDED_KEY] = False
                goals_meta[CALORIE_GOAL_SEEDED_AT_KEY] = None
                merged_stats[GOALS_META_STATS_KEY] = goals_meta
        if estimated_calorie_goal is not None:
            goals = self._extract_goals(merged_stats)
            goals["calorie_goal"] = estimated_calorie_goal
            merged_stats[GOALS_STATS_KEY] = goals
            goals_meta = self._extract_goals_meta(merged_stats)
            goals_meta[CALORIE_GOAL_SOURCE_KEY] = "tdee_estimate"
            goals_meta[CALORIE_GOAL_SEEDED_KEY] = False
            goals_meta[CALORIE_GOAL_SEEDED_AT_KEY] = None
            merged_stats[GOALS_META_STATS_KEY] = goals_meta
        if merged_stats:
            update_data["stats"] = merged_stats

        pref = await self.repository.upsert_user_preference(user_id, **update_data)
        return self._serialize_preference(pref) or {}


# 单例
diet_service = DietService()
