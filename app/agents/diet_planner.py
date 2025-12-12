# app/agents/diet_planner.py
"""
饮食规划 Agent

负责生成饮食计划：
- 单餐推荐
- 日饮食计划
- 周饮食计划

依赖工具：
- RAGTool: 检索菜谱
- NutritionTool: 计算营养
- SimilarityTool: 食材替换
"""

import uuid
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from app.agents.base import BaseAgent, AgentContext, AgentPlan
from app.cards.base import CardType
from app.cards.meal import MealCard, MealType, DishItem, NutritionInfo, IngredientItem
from app.cards.diet_plan import DailyDietPlanCard, WeeklyDietPlanCard, Weekday
from app.tools.rag import RAGTool, RAGQueryInput
from app.tools.nutrition import NutritionTool
from app.tools.similarity import SimilarityTool


class DietPlannerAgent(BaseAgent[WeeklyDietPlanCard]):
    """
    饮食规划 Agent
    
    输入：用户需求（如"帮我规划下周的减脂餐"）
    输出：WeeklyDietPlanCard
    """
    
    name = "diet_planner"
    description = "饮食规划，根据用户目标和约束生成个性化餐饮计划"
    output_card_type = WeeklyDietPlanCard
    
    def __init__(self, llm=None, rag_tool: Optional[RAGTool] = None):
        super().__init__(llm=llm)
        self.rag_tool = rag_tool or RAGTool()
        self.nutrition_tool = NutritionTool()
        self.similarity_tool = SimilarityTool()
        self._tools = [self.rag_tool, self.nutrition_tool, self.similarity_tool]
    
    async def plan(self, task: str, context: AgentContext) -> AgentPlan:
        """规划饮食计划生成步骤"""
        
        # 从约束中提取关键信息
        target_calories = context.constraints.get("target_daily_calories", 2000)
        target_protein = context.constraints.get("min_daily_protein_g", 100)
        dietary_restrictions = context.preferences.get("dietary_restrictions", [])
        
        # 生成执行计划
        steps = [
            f"1. 确定营养目标：{target_calories}kcal/天，蛋白质{target_protein}g/天",
            "2. 为每天的每餐检索合适的菜谱",
            "3. 计算每餐营养，确保达标",
            "4. 检查食材限制，必要时替换",
            "5. 生成完整的周计划卡片",
        ]
        
        if dietary_restrictions:
            steps.insert(1, f"1.5. 注意饮食限制：{', '.join(dietary_restrictions)}")
        
        return AgentPlan(
            plan_id=f"plan_{uuid.uuid4().hex[:8]}",
            steps=steps,
            tools_needed=["rag_query", "nutrition_query", "ingredient_substitute"],
            reasoning=f"用户需要饮食计划，目标热量{target_calories}kcal，需要检索菜谱并计算营养",
        )
    
    async def execute(self, plan: AgentPlan, context: AgentContext) -> WeeklyDietPlanCard:
        """执行饮食计划生成"""
        
        # 提取约束
        target_calories = context.constraints.get("target_daily_calories", 2000)
        target_protein = context.constraints.get("min_daily_protein_g", 100)
        exclude_ingredients = []
        
        # 解析饮食限制
        for restriction in context.preferences.get("dietary_restrictions", []):
            if "不吃:" in restriction or "过敏:" in restriction or "不耐受:" in restriction:
                ingredient = restriction.split(":")[-1].strip()
                exclude_ingredients.append(ingredient)
        
        # 计算每餐目标
        breakfast_ratio = 0.25
        lunch_ratio = 0.35
        dinner_ratio = 0.35
        snack_ratio = 0.05
        
        # 生成周计划
        start_date = date.today()
        # 调整到下周一
        days_until_monday = (7 - start_date.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        start_date = start_date + timedelta(days=days_until_monday)
        
        weekdays = list(Weekday)
        daily_plans = []
        
        for i, weekday in enumerate(weekdays):
            plan_date = start_date + timedelta(days=i)
            
            # 生成当天的餐食
            meals = []
            
            # 早餐
            breakfast = await self._generate_meal(
                meal_type=MealType.BREAKFAST,
                target_calories=int(target_calories * breakfast_ratio),
                target_protein=target_protein * breakfast_ratio,
                exclude_ingredients=exclude_ingredients,
                query_hint="营养早餐 高蛋白",
            )
            meals.append(breakfast)
            
            # 午餐
            lunch = await self._generate_meal(
                meal_type=MealType.LUNCH,
                target_calories=int(target_calories * lunch_ratio),
                target_protein=target_protein * lunch_ratio,
                exclude_ingredients=exclude_ingredients,
                query_hint="均衡午餐 荤素搭配",
            )
            meals.append(lunch)
            
            # 晚餐
            dinner = await self._generate_meal(
                meal_type=MealType.DINNER,
                target_calories=int(target_calories * dinner_ratio),
                target_protein=target_protein * dinner_ratio,
                exclude_ingredients=exclude_ingredients,
                query_hint="清淡晚餐 易消化",
            )
            meals.append(dinner)
            
            # 创建日计划
            daily_plan = DailyDietPlanCard(
                card_id=f"daily_diet_{plan_date.isoformat()}",
                user_id=context.user_id,
                plan_date=plan_date,
                weekday=weekday,
                meals=meals,
                target_calories=target_calories,
                target_protein_g=target_protein,
                source_agent=self.name,
            )
            daily_plans.append(daily_plan)
        
        # 创建周计划
        weekly_plan = WeeklyDietPlanCard(
            card_id=f"weekly_diet_{start_date.isoformat()}",
            user_id=context.user_id,
            week_start_date=start_date,
            daily_plans=daily_plans,
            weekly_calorie_target=target_calories * 7,
            weekly_protein_target=target_protein * 7,
            overview=f"周饮食计划：目标{target_calories}kcal/天，蛋白质{target_protein}g/天",
            source_agent=self.name,
        )
        
        return weekly_plan
    
    async def _generate_meal(
        self,
        meal_type: MealType,
        target_calories: int,
        target_protein: float,
        exclude_ingredients: List[str],
        query_hint: str,
    ) -> MealCard:
        """生成单餐"""
        
        # 使用 RAG 检索菜谱
        rag_input = RAGQueryInput(
            query=query_hint,
            exclude_ingredients=exclude_ingredients,
            top_k=3,
        )
        rag_result = await self.rag_tool.execute(rag_input)
        
        # 构建菜品列表
        dishes = []
        for recipe in rag_result.recipes[:2]:  # 每餐最多2道菜
            # 估算营养（简化实现）
            estimated_nutrition = NutritionInfo(
                calories=target_calories / 2,
                protein_g=target_protein / 2,
                carbs_g=target_calories / 2 * 0.4 / 4,  # 40% 碳水
                fat_g=target_calories / 2 * 0.3 / 9,   # 30% 脂肪
            )
            
            dish = DishItem(
                dish_id=recipe.recipe_id,
                name=recipe.name,
                description=recipe.description,
                category=recipe.category,
                nutrition=estimated_nutrition,
                cook_time_minutes=recipe.cooking_time_minutes or 30,
                source=recipe.source,
            )
            dishes.append(dish)
        
        # 如果没有从 RAG 获取到菜谱，使用默认菜品
        if not dishes:
            dishes = [self._get_default_dish(meal_type, target_calories, target_protein)]
        
        # 设置用餐时间
        meal_times = {
            MealType.BREAKFAST: "08:00",
            MealType.LUNCH: "12:00",
            MealType.DINNER: "18:30",
            MealType.SNACK: "15:00",
            MealType.PRE_WORKOUT: "16:00",
            MealType.POST_WORKOUT: "19:00",
        }
        
        return MealCard(
            card_id=f"meal_{meal_type.value}_{uuid.uuid4().hex[:6]}",
            meal_type=meal_type,
            scheduled_time=meal_times.get(meal_type, "12:00"),
            dishes=dishes,
            source_agent=self.name,
        )
    
    def _get_default_dish(
        self, 
        meal_type: MealType, 
        target_calories: int,
        target_protein: float,
    ) -> DishItem:
        """获取默认菜品（当 RAG 无结果时）"""
        
        defaults = {
            MealType.BREAKFAST: ("燕麦牛奶", "燕麦+牛奶+水果的健康早餐"),
            MealType.LUNCH: ("鸡胸肉沙拉", "低脂高蛋白的健康午餐"),
            MealType.DINNER: ("清蒸鱼配蔬菜", "清淡易消化的晚餐"),
            MealType.SNACK: ("坚果酸奶", "健康的加餐选择"),
        }
        
        name, desc = defaults.get(meal_type, ("健康餐", "均衡营养的一餐"))
        
        return DishItem(
            name=name,
            description=desc,
            nutrition=NutritionInfo(
                calories=target_calories,
                protein_g=target_protein,
                carbs_g=target_calories * 0.4 / 4,
                fat_g=target_calories * 0.3 / 9,
            ),
            cook_time_minutes=20,
            difficulty=2,
        )
    
    async def reflect(
        self, 
        output: WeeklyDietPlanCard, 
        context: AgentContext,
        max_iterations: int = 2,
    ) -> tuple[WeeklyDietPlanCard, List[str]]:
        """反思并修复饮食计划"""
        
        issues = []
        
        # 验证约束
        violations = output.validate_constraints(context.constraints)
        issues.extend(violations)
        
        # 检查每天的热量平衡
        for daily in output.daily_plans:
            nutrition = daily.total_nutrition
            target = daily.target_calories or context.constraints.get("target_daily_calories", 2000)
            
            # 热量偏差检查
            deviation = abs(nutrition.calories - target) / target
            if deviation > 0.2:  # 偏差超过20%
                issues.append(
                    f"{daily.plan_date}: 热量偏差过大 ({nutrition.calories:.0f} vs 目标{target})"
                )
        
        # TODO: 阶段二实现自动修复逻辑
        # 当前只记录问题，不自动修复
        
        return output, issues
    
    def get_system_prompt(self, context: AgentContext) -> str:
        """生成饮食规划专用的系统提示词"""
        return f"""你是 CookHero 的饮食规划助手，专注于为用户创建个性化的健康饮食计划。

{context.to_prompt_context()}

你的职责：
1. 根据用户的营养目标（热量、蛋白质等）规划每餐
2. 考虑用户的饮食限制（过敏、不耐受、偏好）
3. 确保饮食多样性和营养均衡
4. 选择符合用户烹饪能力的菜谱

输出要求：
- 必须输出结构化的饮食计划（JSON格式）
- 每餐包含具体菜品和营养信息
- 如有约束无法满足，明确说明
"""
