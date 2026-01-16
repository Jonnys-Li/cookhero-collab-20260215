"""
Agent/Tool/Skill 注册中心

集中管理所有 Agent、Tool、Skill 的注册和获取。
"""

import logging
from typing import TYPE_CHECKING, Optional, Type

from app.agent.types import AgentConfig
from app.agent.tools.base import BaseTool, ToolExecutor

if TYPE_CHECKING:
    from app.agent.base import BaseAgent

logger = logging.getLogger(__name__)


class AgentRegistry:
    """
    Agent/Tool/Skill 注册中心。

    提供统一的注册、获取接口。
    """

    # Agent 注册表：name -> (agent_class, config)
    _agents: dict[str, tuple[Type["BaseAgent"], AgentConfig]] = {}

    # Tool 注册表：name -> tool_instance
    _tools: dict[str, BaseTool] = {}

    # ==================== Agent Operations ====================

    @classmethod
    def register_agent(
        cls,
        agent_cls: Type["BaseAgent"],
        config: AgentConfig,
    ) -> None:
        """
        注册 Agent。

        Args:
            agent_cls: Agent 类
            config: Agent 配置
        """
        cls._agents[config.name] = (agent_cls, config)
        logger.info(f"Registered agent: {config.name}")

    @classmethod
    def get_agent(cls, name: str) -> "BaseAgent":
        """
        获取 Agent 实例。

        Args:
            name: Agent 名称

        Returns:
            Agent 实例

        Raises:
            KeyError: 如果 Agent 不存在
        """
        if name not in cls._agents:
            raise KeyError(f"Agent '{name}' not found")

        agent_cls, config = cls._agents[name]
        return agent_cls(config)

    @classmethod
    def get_agent_config(cls, name: str) -> AgentConfig:
        """
        获取 Agent 配置。

        Args:
            name: Agent 名称

        Returns:
            Agent 配置
        """
        if name not in cls._agents:
            raise KeyError(f"Agent '{name}' not found")
        return cls._agents[name][1]

    @classmethod
    def list_agents(cls) -> list[str]:
        """列出所有已注册的 Agent 名称。"""
        return list(cls._agents.keys())

    @classmethod
    def has_agent(cls, name: str) -> bool:
        """检查 Agent 是否已注册。"""
        return name in cls._agents

    # ==================== Tool Operations ====================

    @classmethod
    def register_tool(cls, tool: BaseTool) -> None:
        """
        注册 Tool。

        Args:
            tool: Tool 实例
        """
        cls._tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name}")

    @classmethod
    def get_tool(cls, name: str) -> Optional[BaseTool]:
        """
        获取 Tool 实例。

        Args:
            name: Tool 名称

        Returns:
            Tool 实例，如果不存在返回 None
        """
        return cls._tools.get(name)

    @classmethod
    def get_tool_schemas(cls, names: Optional[list[str]] = None) -> list[dict]:
        """
        获取 Tool schemas。

        Args:
            names: Tool 名称列表，None 表示全部

        Returns:
            OpenAI tool schema 列表
        """
        if names is None:
            return [t.to_openai_schema() for t in cls._tools.values()]
        return [cls._tools[n].to_openai_schema() for n in names if n in cls._tools]

    @classmethod
    def create_tool_executor(
        cls,
        tool_names: Optional[list[str]] = None,
    ) -> ToolExecutor:
        """
        创建 Tool 执行器。

        Args:
            tool_names: 要包含的 Tool 名称列表，None 表示全部

        Returns:
            ToolExecutor 实例
        """
        if tool_names is None:
            tools = cls._tools
        else:
            tools = {n: cls._tools[n] for n in tool_names if n in cls._tools}
        return ToolExecutor(tools)

    @classmethod
    def list_tools(cls) -> list[str]:
        """列出所有已注册的 Tool 名称。"""
        return list(cls._tools.keys())

    @classmethod
    def has_tool(cls, name: str) -> bool:
        """检查 Tool 是否已注册。"""
        return name in cls._tools


# 装饰器：注册 Agent
def register_agent(config: AgentConfig):
    """
    Agent 注册装饰器。

    Usage:
        @register_agent(AgentConfig(name="my_agent", ...))
        class MyAgent(BaseAgent):
            ...
    """

    def decorator(cls: Type["BaseAgent"]) -> Type["BaseAgent"]:
        AgentRegistry.register_agent(cls, config)
        return cls

    return decorator


# 装饰器：注册 Tool
def register_tool(cls: Type[BaseTool]) -> Type[BaseTool]:
    """
    Tool 注册装饰器。

    Usage:
        @register_tool
        class MyTool(BaseTool):
            name = "my_tool"
            ...
    """
    instance = cls()
    AgentRegistry.register_tool(instance)
    return cls
