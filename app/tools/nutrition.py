# app/tools/nutrition.py
"""
营养计算工具

提供：
- 食物营养信息查询
- 热量估算
- 营养目标计算
- 餐食营养汇总
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.tools.base import BaseTool, ToolMetadata
from app.cards.meal import NutritionInfo


# ============== 常见食物营养数据库（简化版，实际应接入专业 API）==============
NUTRITION_DATABASE: Dict[str, Dict[str, float]] = {
    # 格式: 食物名 -> 每100g的营养（kcal, 蛋白质g, 碳水g, 脂肪g）
    "鸡胸肉": {"calories": 165, "protein": 31, "carbs": 0, "fat": 3.6},
    "鸡蛋": {"calories": 155, "protein": 13, "carbs": 1.1, "fat": 11},
    "牛肉": {"calories": 250, "protein": 26, "carbs": 0, "fat": 15},
    "猪肉": {"calories": 242, "protein": 27, "carbs": 0, "fat": 14},
    "三文鱼": {"calories": 208, "protein": 20, "carbs": 0, "fat": 13},
    "虾": {"calories": 99, "protein": 24, "carbs": 0.2, "fat": 0.3},
    "豆腐": {"calories": 76, "protein": 8, "carbs": 1.9, "fat": 4.8},
    "米饭": {"calories": 130, "protein": 2.7, "carbs": 28, "fat": 0.3},
    "面条": {"calories": 138, "protein": 5, "carbs": 25, "fat": 2},
    "燕麦": {"calories": 389, "protein": 17, "carbs": 66, "fat": 7},
    "西兰花": {"calories": 34, "protein": 2.8, "carbs": 7, "fat": 0.4},
    "菠菜": {"calories": 23, "protein": 2.9, "carbs": 3.6, "fat": 0.4},
    "胡萝卜": {"calories": 41, "protein": 0.9, "carbs": 10, "fat": 0.2},
    "西红柿": {"calories": 18, "protein": 0.9, "carbs": 3.9, "fat": 0.2},
    "土豆": {"calories": 77, "protein": 2, "carbs": 17, "fat": 0.1},
    "苹果": {"calories": 52, "protein": 0.3, "carbs": 14, "fat": 0.2},
    "香蕉": {"calories": 89, "protein": 1.1, "carbs": 23, "fat": 0.3},
    "牛奶": {"calories": 42, "protein": 3.4, "carbs": 5, "fat": 1},
    "酸奶": {"calories": 59, "protein": 10, "carbs": 3.6, "fat": 0.7},
    "橄榄油": {"calories": 884, "protein": 0, "carbs": 0, "fat": 100},
}


class NutritionQueryInput(BaseModel):
    """营养查询输入"""
    food_name: str = Field(..., description="食物名称")
    amount_g: float = Field(default=100, ge=0, description="重量（克）")


class NutritionResult(BaseModel):
    """营养查询结果"""
    food_name: str
    amount_g: float
    nutrition: NutritionInfo
    found_in_database: bool = True
    notes: Optional[str] = None


class MealNutritionInput(BaseModel):
    """餐食营养计算输入"""
    items: List[Dict[str, Any]] = Field(
        ..., 
        description="食物列表，每项包含 name 和 amount_g"
    )


class MealNutritionResult(BaseModel):
    """餐食营养结果"""
    items: List[NutritionResult]
    total: NutritionInfo
    summary: str


class TDEEInput(BaseModel):
    """TDEE 计算输入"""
    weight_kg: float = Field(..., ge=20, le=300)
    height_cm: float = Field(..., ge=50, le=250)
    age: int = Field(..., ge=1, le=120)
    gender: str = Field(..., description="male 或 female")
    activity_level: str = Field(
        default="moderate",
        description="sedentary/light/moderate/active/very_active"
    )


class TDEEResult(BaseModel):
    """TDEE 计算结果"""
    bmr: float = Field(..., description="基础代谢率")
    tdee: float = Field(..., description="每日总消耗")
    
    # 不同目标的建议热量
    maintain_calories: float
    mild_loss_calories: float  # 轻度减脂 (-250)
    loss_calories: float       # 减脂 (-500)
    mild_gain_calories: float  # 轻度增重 (+250)
    gain_calories: float       # 增重 (+500)
    
    # 宏量素建议
    protein_g_min: float
    protein_g_max: float


class NutritionTool(BaseTool[NutritionQueryInput, NutritionResult]):
    """
    营养查询工具
    
    查询食物的营养信息（热量、蛋白质、碳水、脂肪）
    """
    
    input_schema = NutritionQueryInput
    output_schema = NutritionResult
    metadata = ToolMetadata(
        name="nutrition_query",
        description="查询食物的营养信息。输入食物名称和重量，返回热量、蛋白质、碳水化合物、脂肪等营养数据。",
        usage_hint="food_name 使用中文食物名，如'鸡胸肉'、'米饭'",
        examples=[
            "查询 100g 鸡胸肉的营养",
            "查询 200g 米饭的热量",
        ],
    )
    
    def __init__(self, database: Optional[Dict] = None):
        self.database = database or NUTRITION_DATABASE
    
    async def execute(self, input_data: NutritionQueryInput) -> NutritionResult:
        """执行营养查询"""
        food_name = input_data.food_name
        amount_g = input_data.amount_g
        
        # 查找食物（支持模糊匹配）
        nutrition_per_100g = None
        matched_name = food_name
        
        for name, data in self.database.items():
            if name in food_name or food_name in name:
                nutrition_per_100g = data
                matched_name = name
                break
        
        if nutrition_per_100g:
            # 按重量计算
            ratio = amount_g / 100
            nutrition = NutritionInfo(
                calories=nutrition_per_100g["calories"] * ratio,
                protein_g=nutrition_per_100g["protein"] * ratio,
                carbs_g=nutrition_per_100g["carbs"] * ratio,
                fat_g=nutrition_per_100g["fat"] * ratio,
            )
            return NutritionResult(
                food_name=matched_name,
                amount_g=amount_g,
                nutrition=nutrition,
                found_in_database=True,
            )
        else:
            # 未找到，返回估算值
            return NutritionResult(
                food_name=food_name,
                amount_g=amount_g,
                nutrition=NutritionInfo(
                    calories=100 * (amount_g / 100),  # 默认估算
                    protein_g=5 * (amount_g / 100),
                    carbs_g=15 * (amount_g / 100),
                    fat_g=3 * (amount_g / 100),
                ),
                found_in_database=False,
                notes=f"'{food_name}' 不在数据库中，已使用估算值",
            )
    
    async def calculate_meal_nutrition(
        self, items: List[Dict[str, Any]]
    ) -> MealNutritionResult:
        """
        计算一餐的总营养
        
        Args:
            items: [{"name": "鸡胸肉", "amount_g": 150}, ...]
        """
        results = []
        total = NutritionInfo()
        
        for item in items:
            input_data = NutritionQueryInput(
                food_name=item.get("name", ""),
                amount_g=item.get("amount_g", 100),
            )
            result = await self.execute(input_data)
            results.append(result)
            total = total + result.nutrition
        
        return MealNutritionResult(
            items=results,
            total=total,
            summary=total.to_summary(),
        )
    
    def calculate_tdee(self, input_data: TDEEInput) -> TDEEResult:
        """
        计算 TDEE（每日总消耗热量）
        使用 Mifflin-St Jeor 公式
        """
        # BMR 计算
        if input_data.gender.lower() == "male":
            bmr = 10 * input_data.weight_kg + 6.25 * input_data.height_cm - 5 * input_data.age + 5
        else:
            bmr = 10 * input_data.weight_kg + 6.25 * input_data.height_cm - 5 * input_data.age - 161
        
        # 活动系数
        activity_multipliers = {
            "sedentary": 1.2,
            "light": 1.375,
            "moderate": 1.55,
            "active": 1.725,
            "very_active": 1.9,
        }
        multiplier = activity_multipliers.get(input_data.activity_level.lower(), 1.55)
        tdee = bmr * multiplier
        
        # 蛋白质建议 (1.6-2.2g/kg 体重)
        protein_min = input_data.weight_kg * 1.6
        protein_max = input_data.weight_kg * 2.2
        
        return TDEEResult(
            bmr=round(bmr),
            tdee=round(tdee),
            maintain_calories=round(tdee),
            mild_loss_calories=round(tdee - 250),
            loss_calories=round(tdee - 500),
            mild_gain_calories=round(tdee + 250),
            gain_calories=round(tdee + 500),
            protein_g_min=round(protein_min),
            protein_g_max=round(protein_max),
        )
