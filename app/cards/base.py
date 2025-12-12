# app/cards/base.py
"""
Structure Card 基类

所有结构化输出卡片的基类，定义：
- 通用字段（ID、时间戳、状态）
- 序列化/反序列化
- 验证逻辑
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CardType(str, Enum):
    """卡片类型"""
    MEAL = "meal"
    DAILY_DIET = "daily_diet"
    WEEKLY_DIET = "weekly_diet"
    EXERCISE = "exercise"
    DAILY_TRAINING = "daily_training"
    WEEKLY_TRAINING = "weekly_training"
    COMBINED_LIFESTYLE = "combined_lifestyle"
    RECIPE = "recipe"
    SHOPPING_LIST = "shopping_list"


class CardStatus(str, Enum):
    """卡片状态"""
    DRAFT = "draft"              # 草稿
    CONFIRMED = "confirmed"      # 已确认
    IN_PROGRESS = "in_progress"  # 执行中
    COMPLETED = "completed"      # 已完成
    MODIFIED = "modified"        # 已修改
    CANCELLED = "cancelled"      # 已取消


class BaseCard(BaseModel):
    """
    Structure Card 基类
    
    所有输出卡片都继承此类，确保：
    1. 统一的 ID 和时间戳管理
    2. 状态追踪
    3. 可被后续 Agent 消费
    4. 可直接序列化给前端
    """
    
    # 标识
    card_id: str = Field(..., description="卡片唯一ID")
    card_type: CardType = Field(..., description="卡片类型")
    
    # 关联
    user_id: Optional[str] = Field(None, description="所属用户")
    parent_card_id: Optional[str] = Field(None, description="父卡片ID（用于层级结构）")
    
    # 状态
    status: CardStatus = Field(default=CardStatus.DRAFT)
    
    # 时间
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    valid_from: Optional[datetime] = Field(None, description="生效开始时间")
    valid_until: Optional[datetime] = Field(None, description="生效结束时间")
    
    # 来源追踪
    created_by: str = Field(default="system", description="创建者：user/agent_name/system")
    source_agent: Optional[str] = Field(None, description="生成此卡片的 Agent")
    
    # 元数据
    tags: List[str] = Field(default_factory=list, description="标签")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="扩展元数据")
    
    # 版本控制
    version: int = Field(default=1, description="版本号")
    previous_version_id: Optional[str] = Field(None, description="上一版本ID")
    
    def mark_updated(self) -> "BaseCard":
        """标记为已更新"""
        self.updated_at = datetime.now()
        self.version += 1
        self.status = CardStatus.MODIFIED
        return self
    
    def confirm(self) -> "BaseCard":
        """确认卡片"""
        self.status = CardStatus.CONFIRMED
        self.updated_at = datetime.now()
        return self
    
    def complete(self) -> "BaseCard":
        """标记完成"""
        self.status = CardStatus.COMPLETED
        self.updated_at = datetime.now()
        return self
    
    def cancel(self) -> "BaseCard":
        """取消卡片"""
        self.status = CardStatus.CANCELLED
        self.updated_at = datetime.now()
        return self
    
    def to_summary(self) -> str:
        """
        生成卡片摘要（用于 Agent 上下文）
        子类应重写此方法
        """
        return f"[{self.card_type.value}] {self.card_id}"
    
    def to_display_dict(self) -> Dict[str, Any]:
        """
        转换为前端展示格式
        子类可重写以自定义展示字段
        """
        return self.model_dump(exclude={"metadata", "previous_version_id"})
    
    def validate_constraints(self, constraints: Dict[str, Any]) -> List[str]:
        """
        验证卡片是否满足约束条件
        返回不满足的约束列表
        子类应重写此方法
        """
        return []
    
    class Config:
        use_enum_values = False  # 保留枚举对象
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


class CardCollection(BaseModel):
    """
    卡片集合 - 管理一组相关卡片
    """
    collection_id: str
    cards: List[BaseCard] = Field(default_factory=list)
    
    def add_card(self, card: BaseCard):
        self.cards.append(card)
    
    def get_by_id(self, card_id: str) -> Optional[BaseCard]:
        for card in self.cards:
            if card.card_id == card_id:
                return card
        return None
    
    def get_by_type(self, card_type: CardType) -> List[BaseCard]:
        return [c for c in self.cards if c.card_type == card_type]
    
    def get_active_cards(self) -> List[BaseCard]:
        """获取非取消状态的卡片"""
        return [c for c in self.cards if c.status != CardStatus.CANCELLED]
