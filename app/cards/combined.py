# app/cards/combined.py
"""
综合生活方式计划卡片 - CombinedLifestylePlanCard

整合饮食计划和训练计划，是最终输出给用户的顶层卡片。
支持：
- 饮食和训练的协调（如训练后加餐）
- 冲突检测和自动调整
- 一站式查看和修改
"""

from datetime import date
from typing import Any, Dict, List, Optional
from pydantic import Field

from app.cards.base import BaseCard, CardType
from app.cards.diet_plan import WeeklyDietPlanCard, DailyDietPlanCard, Weekday, WEEKDAY_CN
from app.cards.training_plan import WeeklyTrainingPlanCard, DailyTrainingCard
from app.cards.meal import NutritionInfo


class DailyCombinedCard(BaseCard):
    """单日综合计划"""
    card_type: CardType = Field(default=CardType.COMBINED_LIFESTYLE)
    
    plan_date: date
    weekday: Optional[Weekday] = None
    
    # 子计划
    diet_plan: Optional[DailyDietPlanCard] = None
    training_plan: Optional[DailyTrainingCard] = None
    
    # 每日总结
    summary: Optional[str] = None
    
    @property
    def total_calorie_intake(self) -> float:
        """总热量摄入"""
        if self.diet_plan:
            return self.diet_plan.total_nutrition.calories
        return 0
    
    @property
    def total_calorie_burn(self) -> float:
        """训练消耗热量"""
        if self.training_plan:
            return self.training_plan.total_estimated_calories
        return 0
    
    @property
    def net_calories(self) -> float:
        """净热量 = 摄入 - 消耗"""
        return self.total_calorie_intake - self.total_calorie_burn
    
    def to_summary(self) -> str:
        date_str = self.plan_date.strftime("%m-%d")
        weekday_str = WEEKDAY_CN.get(self.weekday, "") if self.weekday else ""
        
        parts = [f"[{date_str} {weekday_str}]"]
        
        if self.training_plan and not self.training_plan.is_rest_day:
            parts.append(f"训练:{self.training_plan.focus or '有'}")
        
        parts.append(f"摄入:{self.total_calorie_intake:.0f}kcal")
        parts.append(f"消耗:{self.total_calorie_burn:.0f}kcal")
        parts.append(f"净:{self.net_calories:+.0f}kcal")
        
        return " | ".join(parts)


class CombinedLifestylePlanCard(BaseCard):
    """
    综合生活方式周计划
    
    这是 Agent 最终输出的顶层卡片，整合：
    - 周饮食计划
    - 周训练计划
    - 冲突检测结果
    - 营养/训练平衡分析
    """
    card_type: CardType = Field(default=CardType.COMBINED_LIFESTYLE)
    
    # 基本信息
    title: str = Field(..., description="计划标题")
    description: Optional[str] = Field(None, description="计划描述")
    
    # 时间范围
    start_date: date = Field(..., description="开始日期")
    end_date: date = Field(..., description="结束日期")
    
    # 子计划
    diet_plan: Optional[WeeklyDietPlanCard] = None
    training_plan: Optional[WeeklyTrainingPlanCard] = None
    
    # 每日综合视图（由系统自动生成）
    daily_combined: List[DailyCombinedCard] = Field(default_factory=list)
    
    # 目标和约束
    goals_summary: List[str] = Field(default_factory=list, description="关联的目标摘要")
    constraints_applied: Dict[str, Any] = Field(default_factory=dict, description="应用的约束条件")
    
    # 冲突和建议
    conflicts: List[Dict[str, Any]] = Field(default_factory=list, description="检测到的冲突")
    recommendations: List[str] = Field(default_factory=list, description="优化建议")
    
    # 统计摘要
    @property
    def total_week_calories_intake(self) -> float:
        """周总摄入热量"""
        if self.diet_plan:
            return self.diet_plan.total_nutrition.calories
        return 0
    
    @property
    def total_week_calories_burn(self) -> float:
        """周总训练消耗"""
        if self.training_plan:
            return sum(d.total_estimated_calories for d in self.training_plan.daily_plans)
        return 0
    
    @property
    def average_daily_protein(self) -> float:
        """日均蛋白质摄入"""
        if self.diet_plan:
            return self.diet_plan.daily_average_nutrition.protein_g
        return 0
    
    def build_daily_combined(self) -> List[DailyCombinedCard]:
        """
        构建每日综合视图
        将饮食和训练计划按日期合并
        """
        daily_map: Dict[date, DailyCombinedCard] = {}
        
        # 添加饮食计划
        if self.diet_plan:
            for daily_diet in self.diet_plan.daily_plans:
                d = daily_diet.plan_date
                if d not in daily_map:
                    daily_map[d] = DailyCombinedCard(
                        card_id=f"{self.card_id}_daily_{d.isoformat()}",
                        plan_date=d,
                        weekday=daily_diet.weekday,
                    )
                daily_map[d].diet_plan = daily_diet
        
        # 添加训练计划
        if self.training_plan:
            for daily_training in self.training_plan.daily_plans:
                d = daily_training.plan_date
                if d not in daily_map:
                    daily_map[d] = DailyCombinedCard(
                        card_id=f"{self.card_id}_daily_{d.isoformat()}",
                        plan_date=d,
                        weekday=daily_training.weekday,
                    )
                daily_map[d].training_plan = daily_training
        
        # 按日期排序
        self.daily_combined = sorted(daily_map.values(), key=lambda x: x.plan_date)
        return self.daily_combined
    
    def detect_conflicts(self) -> List[Dict[str, Any]]:
        """
        检测饮食和训练计划之间的冲突
        """
        conflicts = []
        
        if not self.daily_combined:
            self.build_daily_combined()
        
        for daily in self.daily_combined:
            # 检查训练日是否有足够的碳水恢复
            if daily.training_plan and not daily.training_plan.is_rest_day:
                if daily.training_plan.total_duration > 60:  # 长时间训练
                    if daily.diet_plan:
                        carbs = daily.diet_plan.total_nutrition.carbs_g
                        if carbs < 200:  # 简单阈值
                            conflicts.append({
                                "type": "insufficient_carbs_for_training",
                                "date": daily.plan_date.isoformat(),
                                "message": f"训练日({daily.training_plan.total_duration}分钟)碳水摄入不足({carbs:.0f}g)"
                            })
            
            # 检查热量平衡
            if daily.net_calories < -1000:  # 热量缺口过大
                conflicts.append({
                    "type": "excessive_calorie_deficit",
                    "date": daily.plan_date.isoformat(),
                    "message": f"热量缺口过大：{daily.net_calories:.0f}kcal，可能影响恢复"
                })
        
        self.conflicts = conflicts
        return conflicts
    
    def generate_recommendations(self) -> List[str]:
        """
        生成优化建议
        """
        recommendations = []
        
        # 基于冲突生成建议
        for conflict in self.conflicts:
            if conflict["type"] == "insufficient_carbs_for_training":
                recommendations.append(f"建议在 {conflict['date']} 训练后增加碳水化合物摄入")
            elif conflict["type"] == "excessive_calorie_deficit":
                recommendations.append(f"建议在 {conflict['date']} 适当增加热量摄入或减少训练强度")
        
        # 蛋白质检查
        if self.average_daily_protein < 1.5 * 75:  # 假设体重75kg，每kg需要1.5g蛋白质
            recommendations.append("日均蛋白质摄入偏低，建议增加蛋白质丰富的食物")
        
        self.recommendations = recommendations
        return recommendations
    
    def to_summary(self) -> str:
        """生成摘要"""
        period = f"{self.start_date.strftime('%m-%d')} - {self.end_date.strftime('%m-%d')}"
        return (
            f"[{self.title}] {period}\n"
            f"周摄入: {self.total_week_calories_intake:.0f}kcal | "
            f"周消耗: {self.total_week_calories_burn:.0f}kcal | "
            f"日均蛋白: {self.average_daily_protein:.0f}g\n"
            f"冲突: {len(self.conflicts)}项 | 建议: {len(self.recommendations)}项"
        )
    
    def validate_constraints(self, constraints: Dict[str, Any]) -> List[str]:
        """验证所有约束"""
        violations = []
        
        # 验证饮食计划
        if self.diet_plan:
            diet_violations = self.diet_plan.validate_constraints(constraints)
            violations.extend(diet_violations)
        
        # 验证训练计划
        if self.training_plan:
            training_violations = self.training_plan.validate_constraints(constraints)
            violations.extend(training_violations)
        
        # 检测冲突
        self.detect_conflicts()
        for conflict in self.conflicts:
            violations.append(conflict["message"])
        
        return violations
    
    def to_display_dict(self) -> Dict[str, Any]:
        """前端展示格式"""
        if not self.daily_combined:
            self.build_daily_combined()
        
        return {
            "card_id": self.card_id,
            "title": self.title,
            "description": self.description,
            "period": f"{self.start_date.isoformat()} - {self.end_date.isoformat()}",
            "summary": {
                "total_calories_intake": self.total_week_calories_intake,
                "total_calories_burn": self.total_week_calories_burn,
                "average_daily_protein": self.average_daily_protein,
            },
            "daily_plans": [
                {
                    "date": d.plan_date.isoformat(),
                    "weekday": WEEKDAY_CN.get(d.weekday, "") if d.weekday else "",
                    "diet_summary": d.diet_plan.to_summary() if d.diet_plan else None,
                    "training_summary": d.training_plan.to_summary() if d.training_plan else None,
                    "net_calories": d.net_calories,
                }
                for d in self.daily_combined
            ],
            "conflicts": self.conflicts,
            "recommendations": self.recommendations,
            "status": self.status.value,
        }

    class Config:
        json_schema_extra = {
            "example": {
                "card_id": "lifestyle_001",
                "title": "半马备战第一周",
                "start_date": "2024-01-08",
                "end_date": "2024-01-14",
                "goals_summary": ["完成半马", "保持2800kcal/天", "蛋白质180g/天"],
            }
        }
