# app/cards/meal.py
"""
餐食卡片 - MealCard

单餐的结构化表示，包含：
- 菜品列表
- 营养信息
- 烹饪信息
- 食材清单
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.cards.base import BaseCard, CardType, CardStatus


class MealType(str, Enum):
    """餐次类型"""
    BREAKFAST = "breakfast"      # 早餐
    LUNCH = "lunch"              # 午餐
    DINNER = "dinner"            # 晚餐
    SNACK = "snack"              # 加餐/零食
    PRE_WORKOUT = "pre_workout"  # 训练前
    POST_WORKOUT = "post_workout"  # 训练后


class IngredientItem(BaseModel):
    """食材条目"""
    name: str = Field(..., description="食材名称")
    amount: float = Field(..., description="用量数值")
    unit: str = Field(default="g", description="单位：g, ml, 个, 勺等")
    category: Optional[str] = Field(None, description="分类：肉类, 蔬菜, 调料等")
    notes: Optional[str] = Field(None, description="备注：如'切丁', '去皮'")
    
    def to_string(self) -> str:
        result = f"{self.name} {self.amount}{self.unit}"
        if self.notes:
            result += f"（{self.notes}）"
        return result


class NutritionInfo(BaseModel):
    """营养信息"""
    calories: float = Field(0, ge=0, description="热量 (kcal)")
    protein_g: float = Field(0, ge=0, description="蛋白质 (g)")
    carbs_g: float = Field(0, ge=0, description="碳水化合物 (g)")
    fat_g: float = Field(0, ge=0, description="脂肪 (g)")
    fiber_g: float = Field(0, ge=0, description="膳食纤维 (g)")
    sodium_mg: float = Field(0, ge=0, description="钠 (mg)")
    sugar_g: float = Field(0, ge=0, description="糖 (g)")
    
    # 可选的详细信息
    saturated_fat_g: Optional[float] = None
    cholesterol_mg: Optional[float] = None
    potassium_mg: Optional[float] = None
    
    def __add__(self, other: "NutritionInfo") -> "NutritionInfo":
        """支持营养信息相加"""
        return NutritionInfo(
            calories=self.calories + other.calories,
            protein_g=self.protein_g + other.protein_g,
            carbs_g=self.carbs_g + other.carbs_g,
            fat_g=self.fat_g + other.fat_g,
            fiber_g=self.fiber_g + other.fiber_g,
            sodium_mg=self.sodium_mg + other.sodium_mg,
            sugar_g=self.sugar_g + other.sugar_g,
        )
    
    def to_summary(self) -> str:
        return f"{self.calories:.0f}kcal | 蛋白{self.protein_g:.0f}g | 碳水{self.carbs_g:.0f}g | 脂肪{self.fat_g:.0f}g"


class DishItem(BaseModel):
    """菜品条目"""
    dish_id: Optional[str] = Field(None, description="菜谱ID（如来自 RAG）")
    name: str = Field(..., description="菜品名称")
    description: Optional[str] = Field(None, description="简短描述")
    
    # 食材和营养
    ingredients: List[IngredientItem] = Field(default_factory=list)
    nutrition: NutritionInfo = Field(default_factory=NutritionInfo)
    
    # 烹饪信息
    prep_time_minutes: int = Field(0, ge=0, description="准备时间")
    cook_time_minutes: int = Field(0, ge=0, description="烹饪时间")
    difficulty: int = Field(3, ge=1, le=5, description="难度 1-5")
    
    # 分类
    cuisine: Optional[str] = Field(None, description="菜系：川菜, 粤菜等")
    tags: List[str] = Field(default_factory=list, description="标签：低脂, 高蛋白等")
    
    # 来源
    source: Optional[str] = Field(None, description="来源：HowToCook, 用户自建等")
    recipe_url: Optional[str] = Field(None, description="菜谱链接")
    
    @property
    def total_time_minutes(self) -> int:
        return self.prep_time_minutes + self.cook_time_minutes
    
    def to_summary(self) -> str:
        return f"{self.name} ({self.nutrition.calories:.0f}kcal, {self.total_time_minutes}分钟)"


class MealCard(BaseCard):
    """
    单餐卡片
    
    表示一顿饭的完整信息，可包含多个菜品。
    """
    card_type: CardType = Field(default=CardType.MEAL)
    
    # 餐次信息
    meal_type: MealType
    scheduled_time: Optional[str] = Field(None, description="计划用餐时间，如 '12:00'")
    
    # 菜品列表
    dishes: List[DishItem] = Field(default_factory=list)
    
    # 聚合营养（自动计算）
    @property
    def total_nutrition(self) -> NutritionInfo:
        """汇总所有菜品的营养信息"""
        total = NutritionInfo()
        for dish in self.dishes:
            total = total + dish.nutrition
        return total
    
    # 聚合食材
    @property
    def all_ingredients(self) -> List[IngredientItem]:
        """汇总所有菜品的食材"""
        ingredients = []
        for dish in self.dishes:
            ingredients.extend(dish.ingredients)
        return ingredients
    
    # 烹饪时间
    @property
    def total_cooking_time(self) -> int:
        """总烹饪时间（假设菜品并行制作，取最长时间）"""
        if not self.dishes:
            return 0
        return max(d.total_time_minutes for d in self.dishes)
    
    def add_dish(self, dish: DishItem) -> "MealCard":
        """添加菜品"""
        self.dishes.append(dish)
        self.mark_updated()
        return self
    
    def remove_dish(self, dish_name: str) -> "MealCard":
        """移除菜品"""
        self.dishes = [d for d in self.dishes if d.name != dish_name]
        self.mark_updated()
        return self
    
    def to_summary(self) -> str:
        """生成摘要"""
        meal_names = {
            MealType.BREAKFAST: "早餐",
            MealType.LUNCH: "午餐", 
            MealType.DINNER: "晚餐",
            MealType.SNACK: "加餐",
            MealType.PRE_WORKOUT: "训练前餐",
            MealType.POST_WORKOUT: "训练后餐",
        }
        meal_name = meal_names.get(self.meal_type, self.meal_type.value)
        dishes_str = ", ".join(d.name for d in self.dishes[:3])
        if len(self.dishes) > 3:
            dishes_str += f" 等{len(self.dishes)}道菜"
        
        return f"[{meal_name}] {dishes_str} | {self.total_nutrition.to_summary()}"
    
    def validate_constraints(self, constraints: Dict[str, Any]) -> List[str]:
        """验证约束"""
        violations = []
        nutrition = self.total_nutrition
        
        if "max_calories" in constraints and nutrition.calories > constraints["max_calories"]:
            violations.append(f"热量超标：{nutrition.calories:.0f} > {constraints['max_calories']}")
        
        if "min_protein_g" in constraints and nutrition.protein_g < constraints["min_protein_g"]:
            violations.append(f"蛋白质不足：{nutrition.protein_g:.0f}g < {constraints['min_protein_g']}g")
        
        if "max_cooking_time" in constraints and self.total_cooking_time > constraints["max_cooking_time"]:
            violations.append(f"烹饪时间过长：{self.total_cooking_time}分钟 > {constraints['max_cooking_time']}分钟")
        
        return violations

    class Config:
        json_schema_extra = {
            "example": {
                "card_id": "meal_001",
                "meal_type": "lunch",
                "scheduled_time": "12:00",
                "dishes": [
                    {
                        "name": "水煮鸡胸肉",
                        "nutrition": {"calories": 165, "protein_g": 31, "carbs_g": 0, "fat_g": 3.6},
                        "cook_time_minutes": 15
                    },
                    {
                        "name": "西兰花炒虾仁",
                        "nutrition": {"calories": 120, "protein_g": 18, "carbs_g": 6, "fat_g": 3},
                        "cook_time_minutes": 10
                    }
                ]
            }
        }
