# app/agent/subagents/__init__.py
"""
Subagent 模块

Subagent 是可以被主 Agent 调用的专业化子代理，通过 Tool 机制集成到主 Agent 流程中。
"""

from app.agent.subagents.base import BaseSubagent, SubagentConfig
from app.agent.subagents.registry import SubagentRegistry, subagent_registry
from app.agent.subagents.tool import SubagentTool, create_subagent_tool


def register_builtin_subagents() -> None:
    """
    注册所有内置 Subagent。

    在应用启动时调用此函数。
    """
    from app.agent.subagents.builtin.diet_planner import (
        DietPlannerSubagent,
    )
    from app.agent.subagents.builtin.emotion_support import (
        EmotionSupportSubagent,
    )
    from app.agent.subagents.builtin.cooking_master import (
        CookingMasterSubagent,
    )

    # 注册饮食规划专家
    subagent_registry.register_builtin(
        DietPlannerSubagent,
        DietPlannerSubagent.get_default_config(),
    )

    # 注册情感安抚专家
    subagent_registry.register_builtin(
        EmotionSupportSubagent,
        EmotionSupportSubagent.get_default_config(),
    )

    # 注册烹饪大师
    subagent_registry.register_builtin(
        CookingMasterSubagent,
        CookingMasterSubagent.get_default_config(),
    )


__all__ = [
    "BaseSubagent",
    "SubagentConfig",
    "SubagentRegistry",
    "subagent_registry",
    "SubagentTool",
    "create_subagent_tool",
    "register_builtin_subagents",
]
