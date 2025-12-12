# app/cards/__init__.py
"""
Structure Cards - 结构化输出模块

所有 Agent 的输出都必须是 Structure Card，支持：
- 前端直接渲染
- 后续 Agent 消费和修改
- 持久化存储
- 冲突检测和合并

核心卡片类型：
- MealCard: 单餐卡片
- DailyDietPlanCard: 日饮食计划
- WeeklyDietPlanCard: 周饮食计划
- TrainingPlanCard: 训练计划
- CombinedLifestylePlanCard: 综合生活方式计划
"""

from app.cards.base import BaseCard, CardStatus, CardType
from app.cards.meal import MealCard, MealType, IngredientItem
from app.cards.diet_plan import DailyDietPlanCard, WeeklyDietPlanCard
from app.cards.training_plan import (
    ExerciseCard,
    DailyTrainingCard,
    WeeklyTrainingPlanCard,
    ExerciseType,
)
from app.cards.combined import CombinedLifestylePlanCard

__all__ = [
    # Base
    "BaseCard",
    "CardStatus",
    "CardType",
    # Meal
    "MealCard",
    "MealType",
    "IngredientItem",
    # Diet Plan
    "DailyDietPlanCard",
    "WeeklyDietPlanCard",
    # Training Plan
    "ExerciseCard",
    "DailyTrainingCard",
    "WeeklyTrainingPlanCard",
    "ExerciseType",
    # Combined
    "CombinedLifestylePlanCard",
]
