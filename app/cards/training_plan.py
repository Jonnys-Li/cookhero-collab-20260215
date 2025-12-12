# app/cards/training_plan.py
"""
训练计划卡片

运动/训练计划的结构化表示：
- ExerciseCard: 单项运动
- DailyTrainingCard: 单日训练计划
- WeeklyTrainingPlanCard: 周训练计划
"""

from datetime import date, time
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.cards.base import BaseCard, CardType
from app.cards.diet_plan import Weekday, WEEKDAY_CN


class ExerciseType(str, Enum):
    """运动类型"""
    # 有氧
    RUNNING = "running"
    CYCLING = "cycling"
    SWIMMING = "swimming"
    WALKING = "walking"
    HIIT = "hiit"
    ROWING = "rowing"
    
    # 力量
    STRENGTH = "strength"
    WEIGHT_TRAINING = "weight_training"
    BODYWEIGHT = "bodyweight"
    
    # 柔韧/恢复
    YOGA = "yoga"
    STRETCHING = "stretching"
    FOAM_ROLLING = "foam_rolling"
    
    # 其他
    SPORTS = "sports"  # 球类运动等
    REST = "rest"      # 休息日
    OTHER = "other"


class IntensityLevel(str, Enum):
    """强度级别"""
    RECOVERY = "recovery"    # 恢复
    EASY = "easy"            # 轻松
    MODERATE = "moderate"    # 中等
    HARD = "hard"            # 困难
    MAX = "max"              # 最大强度


INTENSITY_CN = {
    IntensityLevel.RECOVERY: "恢复",
    IntensityLevel.EASY: "轻松",
    IntensityLevel.MODERATE: "中等",
    IntensityLevel.HARD: "困难",
    IntensityLevel.MAX: "最大",
}


class ExerciseCard(BaseCard):
    """
    单项运动卡片
    """
    card_type: CardType = Field(default=CardType.EXERCISE)
    
    # 基本信息
    exercise_type: ExerciseType
    name: str = Field(..., description="运动名称，如'慢跑'、'深蹲'")
    description: Optional[str] = Field(None, description="详细说明")
    
    # 时长/量
    duration_minutes: Optional[int] = Field(None, ge=0, description="时长（分钟）")
    distance_km: Optional[float] = Field(None, ge=0, description="距离（公里）")
    sets: Optional[int] = Field(None, ge=0, description="组数")
    reps: Optional[int] = Field(None, ge=0, description="每组次数")
    weight_kg: Optional[float] = Field(None, ge=0, description="重量（公斤）")
    
    # 强度
    intensity: IntensityLevel = IntensityLevel.MODERATE
    target_heart_rate: Optional[int] = Field(None, description="目标心率")
    target_pace: Optional[str] = Field(None, description="目标配速，如'5:30/km'")
    
    # 热量消耗（估算）
    estimated_calories: Optional[int] = Field(None, ge=0)
    
    # 肌群
    muscle_groups: List[str] = Field(default_factory=list, description="涉及肌群")
    
    # 备注
    notes: Optional[str] = None
    
    def to_summary(self) -> str:
        """生成摘要"""
        parts = [self.name]
        
        if self.duration_minutes:
            parts.append(f"{self.duration_minutes}分钟")
        if self.distance_km:
            parts.append(f"{self.distance_km}km")
        if self.sets and self.reps:
            parts.append(f"{self.sets}组×{self.reps}次")
        if self.weight_kg:
            parts.append(f"{self.weight_kg}kg")
        
        parts.append(f"[{INTENSITY_CN.get(self.intensity, self.intensity.value)}]")
        
        return " ".join(parts)


class DailyTrainingCard(BaseCard):
    """
    单日训练计划卡片
    """
    card_type: CardType = Field(default=CardType.DAILY_TRAINING)
    
    # 日期信息
    plan_date: date = Field(..., description="计划日期")
    weekday: Optional[Weekday] = None
    
    # 训练时段
    scheduled_time: Optional[str] = Field(None, description="计划训练时间")
    
    # 训练内容
    exercises: List[ExerciseCard] = Field(default_factory=list)
    
    # 当日主题
    focus: Optional[str] = Field(None, description="训练重点，如'长距离慢跑'、'上肢力量'")
    
    # 是否休息日
    is_rest_day: bool = Field(default=False)
    
    # 备注
    notes: Optional[str] = None
    
    @property
    def total_duration(self) -> int:
        """总时长"""
        return sum(e.duration_minutes or 0 for e in self.exercises)
    
    @property
    def total_estimated_calories(self) -> int:
        """预计总消耗"""
        return sum(e.estimated_calories or 0 for e in self.exercises)
    
    @property
    def exercise_types(self) -> List[ExerciseType]:
        """涉及的运动类型"""
        return list(set(e.exercise_type for e in self.exercises))
    
    def add_exercise(self, exercise: ExerciseCard) -> "DailyTrainingCard":
        """添加运动"""
        self.exercises.append(exercise)
        self.mark_updated()
        return self
    
    def to_summary(self) -> str:
        """生成摘要"""
        date_str = self.plan_date.strftime("%m-%d")
        weekday_str = WEEKDAY_CN.get(self.weekday, "") if self.weekday else ""
        
        if self.is_rest_day:
            return f"[{date_str} {weekday_str}] 休息日"
        
        focus_str = f" - {self.focus}" if self.focus else ""
        return f"[{date_str} {weekday_str}]{focus_str} | {self.total_duration}分钟 | ~{self.total_estimated_calories}kcal"


class WeeklyTrainingPlanCard(BaseCard):
    """
    周训练计划卡片
    """
    card_type: CardType = Field(default=CardType.WEEKLY_TRAINING)
    
    # 周信息
    week_start_date: date = Field(..., description="周一日期")
    week_number: Optional[int] = Field(None, description="训练周期第几周")
    
    # 每日计划
    daily_plans: List[DailyTrainingCard] = Field(default_factory=list)
    
    # 周目标
    weekly_distance_km: Optional[float] = Field(None, description="周跑量目标")
    weekly_training_hours: Optional[float] = Field(None, description="周训练时长目标")
    
    # 概述
    overview: Optional[str] = Field(None, description="周计划概述")
    goal_description: Optional[str] = Field(None, description="本周目标描述")
    
    @property
    def total_training_minutes(self) -> int:
        """周总训练时长"""
        return sum(d.total_duration for d in self.daily_plans)
    
    @property
    def total_distance(self) -> float:
        """周总距离（跑步、骑行等）"""
        total = 0.0
        for daily in self.daily_plans:
            for exercise in daily.exercises:
                if exercise.distance_km:
                    total += exercise.distance_km
        return total
    
    @property
    def rest_days_count(self) -> int:
        """休息日数量"""
        return sum(1 for d in self.daily_plans if d.is_rest_day)
    
    def get_day(self, weekday: Weekday) -> Optional[DailyTrainingCard]:
        """获取某一天的计划"""
        for daily in self.daily_plans:
            if daily.weekday == weekday:
                return daily
        return None
    
    def set_day(self, daily_plan: DailyTrainingCard) -> "WeeklyTrainingPlanCard":
        """设置某一天的计划"""
        if daily_plan.weekday:
            self.daily_plans = [d for d in self.daily_plans if d.weekday != daily_plan.weekday]
        self.daily_plans.append(daily_plan)
        self.daily_plans.sort(key=lambda d: d.plan_date)
        self.mark_updated()
        return self
    
    def to_summary(self) -> str:
        """生成摘要"""
        start = self.week_start_date.strftime("%m-%d")
        hours = self.total_training_minutes / 60
        return f"[周训练 {start}起] {hours:.1f}h训练 | {self.total_distance:.1f}km | {self.rest_days_count}天休息"
    
    def validate_constraints(self, constraints: Dict[str, Any]) -> List[str]:
        """验证约束"""
        violations = []
        
        # 周跑量
        if self.weekly_distance_km and self.total_distance < self.weekly_distance_km * 0.9:
            violations.append(f"周跑量不足：{self.total_distance:.1f}km < {self.weekly_distance_km}km")
        
        # 休息日检查
        if self.rest_days_count < constraints.get("min_rest_days", 1):
            violations.append(f"休息日不足：{self.rest_days_count}天")
        
        return violations

    class Config:
        json_schema_extra = {
            "example": {
                "card_id": "weekly_training_001",
                "week_start_date": "2024-01-08",
                "weekly_distance_km": 50,
                "overview": "半马备战第一周：建立基础有氧能力",
                "goal_description": "本周重点：3次慢跑，1次长距离，2次力量训练"
            }
        }
