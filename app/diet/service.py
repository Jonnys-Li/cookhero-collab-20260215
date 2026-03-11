# app/diet/service.py
"""
饮食模块业务服务层

提供饮食计划和记录的业务逻辑处理。
"""

import json
import logging
from copy import deepcopy
from datetime import date, datetime, timedelta
from typing import Any, List, Optional

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

logger = logging.getLogger(__name__)

GOAL_KEYS = ("calorie_goal", "protein_goal", "fat_goal", "carbs_goal")
GOALS_STATS_KEY = "goals"
GOALS_META_STATS_KEY = "goals_meta"
CALORIE_GOAL_SOURCE_KEY = "calorie_goal_source"
CALORIE_GOAL_SEEDED_KEY = "calorie_goal_seeded"
CALORIE_GOAL_SEEDED_AT_KEY = "calorie_goal_seeded_at"
DEFAULT_AUTO_CALORIE_GOAL = 1800
TODAY_BUDGET_ADJUSTMENTS_KEY = "today_budget_adjustments"
TODAY_BUDGET_HISTORY_DAYS = 14
TODAY_BUDGET_DAILY_CAP = 150


def get_week_start_date(target_date: date) -> date:
    """获取给定日期所在周的周一日期"""
    return target_date - timedelta(days=target_date.weekday())


class DietService:
    """饮食模块业务服务"""

    def __init__(self, repository: Optional[DietRepository] = None):
        self.repository = repository or diet_repository

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
    def _normalize_parsed_items(items: Any) -> List[dict]:
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
                }
            )
        return normalized

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
        }

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
            dishes.append(
                {
                    "name": dish_name,
                    "weight_g": item.get("weight_g"),
                    "unit": item.get("unit"),
                    "calories": item.get("calories"),
                    "protein": item.get("protein"),
                    "fat": item.get("fat"),
                    "carbs": item.get("carbs"),
                }
            )

        if not dishes:
            return {
                "dishes": [],
                "message": "未识别到清晰食物，请手动补充",
                "source": DataSource.AI_IMAGE.value,
            }

        return {
            "dishes": dishes,
            "message": "识别完成",
            "source": DataSource.AI_IMAGE.value,
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
        return await self.repository.get_weekly_summary(user_id, week_start_date)

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
            if source not in {"explicit", "avg7d", "default1800"}:
                source = "explicit"
            seeded_value = goals_meta.get(CALORIE_GOAL_SEEDED_KEY)
            seeded = bool(seeded_value) if seeded_value is not None else source != "explicit"
            return int(goal_value), source, seeded

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

        return {
            "date": target_date.isoformat(),
            "base_goal": base_goal,
            "today_adjustment": today_adjustment,
            "effective_goal": effective_goal,
            "remaining_adjustment_cap": max(0, TODAY_BUDGET_DAILY_CAP - today_adjustment),
            "adjustment_cap": TODAY_BUDGET_DAILY_CAP,
            "goal_source": goal_source,
            "goal_seeded": goal_seeded,
        }

    async def get_user_preference(self, user_id: str) -> Optional[dict]:
        """获取用户偏好"""
        pref = await self.repository.get_user_preference(user_id)
        return pref.to_dict() if pref else None

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
            return {
                "date": actual_date.isoformat(),
                "base_goal": fallback_goal,
                "today_adjustment": 0,
                "effective_goal": fallback_goal,
                "remaining_adjustment_cap": TODAY_BUDGET_DAILY_CAP,
                "adjustment_cap": TODAY_BUDGET_DAILY_CAP,
                "goal_source": "default1800",
                "goal_seeded": True,
            }

        stats = self._normalize_stats(pref.stats)
        cleaned_entries = self._prune_adjustment_history(
            list(stats.get(TODAY_BUDGET_ADJUSTMENTS_KEY) or []),
            actual_date,
        )
        if cleaned_entries != list(stats.get(TODAY_BUDGET_ADJUSTMENTS_KEY) or []):
            stats[TODAY_BUDGET_ADJUSTMENTS_KEY] = cleaned_entries
            pref = await self.repository.upsert_user_preference(user_id, stats=stats)

        return self._build_budget_snapshot(pref, actual_date)

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
        snapshot.update(
            {
                "requested_delta": requested_delta,
                "applied_delta": applied_delta,
                "capped": applied_delta < requested_delta,
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

        goal_updates = {}
        for key in GOAL_KEYS:
            if key in update_data:
                value = update_data.pop(key)
                if value is not None:
                    goal_updates[key] = value

        existing_pref = await self.repository.get_user_preference(user_id)
        stats_patch = update_data.pop("stats", None)
        merged_stats = self._merge_stats(
            getattr(existing_pref, "stats", None),
            stats_patch,
        )
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
        if merged_stats:
            update_data["stats"] = merged_stats

        pref = await self.repository.upsert_user_preference(user_id, **update_data)
        return pref.to_dict()


# 单例
diet_service = DietService()
