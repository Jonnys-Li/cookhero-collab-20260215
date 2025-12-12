# app/cards/diet_plan.py
"""
饮食计划卡片

日/周饮食计划的结构化表示：
- DailyDietPlanCard: 单日饮食计划
- WeeklyDietPlanCard: 周饮食计划
"""

from datetime import date
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import Field

from app.cards.base import BaseCard, CardType
from app.cards.meal import MealCard, MealType, NutritionInfo


class Weekday(str, Enum):
    """星期"""
    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"


WEEKDAY_CN = {
    Weekday.MONDAY: "周一",
    Weekday.TUESDAY: "周二",
    Weekday.WEDNESDAY: "周三",
    Weekday.THURSDAY: "周四",
    Weekday.FRIDAY: "周五",
    Weekday.SATURDAY: "周六",
    Weekday.SUNDAY: "周日",
}


class DailyDietPlanCard(BaseCard):
    """
    日饮食计划卡片
    
    包含一天内所有餐次的完整计划。
    """
    card_type: CardType = Field(default=CardType.DAILY_DIET)
    
    # 日期信息
    plan_date: date = Field(..., description="计划日期")
    weekday: Optional[Weekday] = Field(None, description="星期几")
    
    # 餐次列表
    meals: List[MealCard] = Field(default_factory=list)
    
    # 目标（用于验证）
    target_calories: Optional[int] = Field(None, description="目标热量")
    target_protein_g: Optional[float] = Field(None, description="目标蛋白质")
    
    # 备注
    notes: Optional[str] = Field(None, description="当日备注，如'长跑日，多补碳水'")
    
    @property
    def total_nutrition(self) -> NutritionInfo:
        """汇总当日所有餐次的营养"""
        total = NutritionInfo()
        for meal in self.meals:
            total = total + meal.total_nutrition
        return total
    
    @property
    def meal_count(self) -> int:
        return len(self.meals)
    
    def get_meal(self, meal_type: MealType) -> Optional[MealCard]:
        """获取指定餐次"""
        for meal in self.meals:
            if meal.meal_type == meal_type:
                return meal
        return None
    
    def set_meal(self, meal: MealCard) -> "DailyDietPlanCard":
        """设置餐次（替换同类型的已有餐次）"""
        self.meals = [m for m in self.meals if m.meal_type != meal.meal_type]
        self.meals.append(meal)
        # 按餐次排序
        order = [MealType.BREAKFAST, MealType.SNACK, MealType.LUNCH, MealType.PRE_WORKOUT,
                 MealType.POST_WORKOUT, MealType.DINNER]
        self.meals.sort(key=lambda m: order.index(m.meal_type) if m.meal_type in order else 99)
        self.mark_updated()
        return self
    
    def to_summary(self) -> str:
        """生成摘要"""
        date_str = self.plan_date.strftime("%m-%d")
        weekday_str = WEEKDAY_CN.get(self.weekday, "") if self.weekday else ""
        nutrition = self.total_nutrition
        
        return f"[{date_str} {weekday_str}] {self.meal_count}餐 | {nutrition.to_summary()}"
    
    def validate_constraints(self, constraints: Dict[str, Any]) -> List[str]:
        """验证约束"""
        violations = []
        nutrition = self.total_nutrition
        
        # 热量约束
        target = self.target_calories or constraints.get("target_daily_calories")
        if target:
            tolerance = constraints.get("calorie_tolerance", 0.1)  # 默认10%容差
            if nutrition.calories < target * (1 - tolerance):
                violations.append(f"热量不足：{nutrition.calories:.0f} < {target}kcal")
            elif nutrition.calories > target * (1 + tolerance):
                violations.append(f"热量超标：{nutrition.calories:.0f} > {target}kcal")
        
        # 蛋白质约束
        min_protein = self.target_protein_g or constraints.get("min_daily_protein_g")
        if min_protein and nutrition.protein_g < min_protein:
            violations.append(f"蛋白质不足：{nutrition.protein_g:.0f}g < {min_protein}g")
        
        # 验证每餐
        for meal in self.meals:
            meal_violations = meal.validate_constraints(constraints)
            violations.extend(meal_violations)
        
        return violations
    
    def to_display_dict(self) -> Dict[str, Any]:
        """前端展示格式"""
        return {
            "card_id": self.card_id,
            "plan_date": self.plan_date.isoformat(),
            "weekday": WEEKDAY_CN.get(self.weekday, "") if self.weekday else "",
            "meals": [
                {
                    "meal_type": meal.meal_type.value,
                    "scheduled_time": meal.scheduled_time,
                    "dishes": [{"name": d.name, "calories": d.nutrition.calories} for d in meal.dishes],
                    "nutrition_summary": meal.total_nutrition.to_summary(),
                }
                for meal in self.meals
            ],
            "total_nutrition": self.total_nutrition.model_dump(),
            "notes": self.notes,
            "status": self.status.value,
        }


class WeeklyDietPlanCard(BaseCard):
    """
    周饮食计划卡片
    
    包含一周七天的完整饮食计划。
    """
    card_type: CardType = Field(default=CardType.WEEKLY_DIET)
    
    # 周信息
    week_start_date: date = Field(..., description="周一日期")
    week_number: Optional[int] = Field(None, description="第几周")
    
    # 每日计划
    daily_plans: List[DailyDietPlanCard] = Field(default_factory=list)
    
    # 周目标
    weekly_calorie_target: Optional[int] = Field(None, description="周总热量目标")
    weekly_protein_target: Optional[float] = Field(None, description="周总蛋白质目标")
    
    # 概述
    overview: Optional[str] = Field(None, description="周计划概述")
    
    @property
    def total_nutrition(self) -> NutritionInfo:
        """汇总一周所有营养"""
        total = NutritionInfo()
        for daily in self.daily_plans:
            total = total + daily.total_nutrition
        return total
    
    @property
    def daily_average_nutrition(self) -> NutritionInfo:
        """每日平均营养"""
        total = self.total_nutrition
        days = len(self.daily_plans) or 1
        return NutritionInfo(
            calories=total.calories / days,
            protein_g=total.protein_g / days,
            carbs_g=total.carbs_g / days,
            fat_g=total.fat_g / days,
            fiber_g=total.fiber_g / days,
            sodium_mg=total.sodium_mg / days,
            sugar_g=total.sugar_g / days,
        )
    
    def get_day(self, weekday: Weekday) -> Optional[DailyDietPlanCard]:
        """获取某一天的计划"""
        for daily in self.daily_plans:
            if daily.weekday == weekday:
                return daily
        return None
    
    def set_day(self, daily_plan: DailyDietPlanCard) -> "WeeklyDietPlanCard":
        """设置某一天的计划"""
        if daily_plan.weekday:
            self.daily_plans = [d for d in self.daily_plans if d.weekday != daily_plan.weekday]
        self.daily_plans.append(daily_plan)
        # 按日期排序
        self.daily_plans.sort(key=lambda d: d.plan_date)
        self.mark_updated()
        return self
    
    def to_summary(self) -> str:
        """生成摘要"""
        start = self.week_start_date.strftime("%m-%d")
        avg = self.daily_average_nutrition
        return f"[周计划 {start}起] {len(self.daily_plans)}天 | 日均: {avg.to_summary()}"
    
    def get_shopping_list(self) -> Dict[str, List[Dict]]:
        """
        生成购物清单
        按食材分类汇总一周所需材料
        """
        ingredients_map: Dict[str, Dict] = {}  # name -> {amount, unit, category}
        
        for daily in self.daily_plans:
            for meal in daily.meals:
                for ingredient in meal.all_ingredients:
                    key = f"{ingredient.name}_{ingredient.unit}"
                    if key in ingredients_map:
                        ingredients_map[key]["amount"] += ingredient.amount
                    else:
                        ingredients_map[key] = {
                            "name": ingredient.name,
                            "amount": ingredient.amount,
                            "unit": ingredient.unit,
                            "category": ingredient.category or "其他",
                        }
        
        # 按分类组织
        by_category: Dict[str, List[Dict]] = {}
        for item in ingredients_map.values():
            category = item["category"]
            if category not in by_category:
                by_category[category] = []
            by_category[category].append({
                "name": item["name"],
                "amount": round(item["amount"], 1),
                "unit": item["unit"],
            })
        
        return by_category
    
    def validate_constraints(self, constraints: Dict[str, Any]) -> List[str]:
        """验证约束"""
        violations = []
        
        # 周总量验证
        total = self.total_nutrition
        if self.weekly_calorie_target:
            tolerance = constraints.get("weekly_calorie_tolerance", 0.05)
            if total.calories < self.weekly_calorie_target * (1 - tolerance):
                violations.append(f"周热量不足：{total.calories:.0f} < {self.weekly_calorie_target}")
            elif total.calories > self.weekly_calorie_target * (1 + tolerance):
                violations.append(f"周热量超标：{total.calories:.0f} > {self.weekly_calorie_target}")
        
        # 验证每天
        for daily in self.daily_plans:
            daily_violations = daily.validate_constraints(constraints)
            if daily_violations:
                violations.append(f"{WEEKDAY_CN.get(daily.weekday, daily.plan_date)}: {', '.join(daily_violations)}")
        
        return violations

    class Config:
        json_schema_extra = {
            "example": {
                "card_id": "weekly_diet_001",
                "week_start_date": "2024-01-08",
                "weekly_calorie_target": 19600,  # 2800 * 7
                "weekly_protein_target": 1260,   # 180 * 7
                "daily_plans": ["..."],
                "overview": "半马备战第一周：高碳水、高蛋白饮食"
            }
        }
