# app/agent/subagents/builtin/emotion_support.py
"""
EmotionSupportSubagent - 情感安抚专家 Subagent

在用户出现饮食内疚、焦虑、自责等场景时，提供支持性反馈与低风险行动建议。
"""

import logging
import re
from typing import Awaitable, Callable, Optional

from app.agent.registry import AgentHub
from app.agent.subagents.base import BaseSubagent, SubagentConfig
from app.agent.types import TraceStep, ToolResult

logger = logging.getLogger(__name__)


EMOTION_SUPPORT_SYSTEM_PROMPT = """你是 CookHero 的情感安抚专家，目标是在用户因饮食而自责、焦虑或内疚时，提供温和、具体、可执行的支持。

## 核心原则

1. **先安抚后建议**：先认可用户情绪，再提供下一步行动。
2. **不羞辱不评判**：禁止使用带有责备、羞辱或恐吓语气的话术。
3. **小步行动**：优先提供当天可执行的小动作，而不是极端补偿方案。
4. **结果导向**：若调用工具，必须把结果翻译成清晰建议，不要只贴工具结果。

## 预算调整策略（低风险）

- 在用户明确担心“今天吃多了”并需要安抚时，可调用 `diet_analysis.adjust_today_budget`。
- `delta_calories` 使用正整数，建议在 50~150 之间。
- 调整仅针对当天临时预算，不修改长期目标。
- 调用前应优先使用 `diet_analysis.get_today_budget` 获取当前状态。

## 输出要求

- 使用简洁的中文 Markdown。
- 结构建议：`情绪回应` + `今日可执行计划` + `下一步提醒`。
- 回答中不要暴露任何工具调用格式或参数细节。"""

LOCAL_TOOL_ALLOWLIST = ["datetime", "diet_analysis", "web_search"]
MCP_TOOL_KEYWORDS = ["weather", "park", "activity", "movie", "music", "fun"]
DAILY_ADJUSTMENT_CAP = 150

CRISIS_PATTERNS = [
    re.compile(r"(不想活|活着没意义|结束生命|自杀|自残)", re.IGNORECASE),
    re.compile(r"(绝食|饿死自己|几天不吃|极端节食)", re.IGNORECASE),
    re.compile(r"(惩罚自己|我不配吃|我很糟糕|讨厌自己)", re.IGNORECASE),
]


class EmotionSupportSubagent(BaseSubagent):
    """情感安抚专家 Subagent。"""

    @classmethod
    def get_default_config(cls) -> SubagentConfig:
        """获取默认配置。"""
        return SubagentConfig(
            name="emotion_support",
            display_name="情感安抚专家",
            description=(
                "当用户因饮食产生内疚、自责、焦虑时，提供情绪安抚和低风险行动建议；"
                "必要时可进行当天临时热量预算调整。"
            ),
            system_prompt=EMOTION_SUPPORT_SYSTEM_PROMPT,
            tools=list(LOCAL_TOOL_ALLOWLIST),
            max_iterations=10,
            enabled=True,
            builtin=True,
            category="wellness",
        )

    async def execute(
        self,
        task: str,
        user_id: Optional[str] = None,
        background: Optional[str] = None,
        event_handler: Optional[Callable[[TraceStep], Awaitable[None]]] = None,
    ) -> ToolResult:
        """
        执行情感安抚任务。

        危机语句使用确定性规则直接分流，不进入 LLM 推理。
        """
        scan_text = self._build_scan_text(task, background)
        if self._is_crisis_text(scan_text):
            content = self._build_crisis_response()
            await self._emit_event(
                event_handler,
                TraceStep(
                    iteration=0,
                    action="subagent_output",
                    content=content,
                    source="subagent",
                    subagent_name=self.name,
                ),
            )
            return ToolResult(
                success=True,
                data={
                    "result": content,
                    "iterations": 0,
                    "mode": "crisis",
                },
            )

        tool_names = self._build_tool_whitelist(user_id)
        combined_background = self._build_background(background, tool_names)
        return await self.run_with_tools(
            task=task,
            user_id=user_id,
            background=combined_background,
            event_handler=event_handler,
            tool_names_override=tool_names,
        )

    def _build_scan_text(self, task: str, background: Optional[str]) -> str:
        if not background:
            return task
        return f"{task}\n{background}"

    def _is_crisis_text(self, text: str) -> bool:
        for pattern in CRISIS_PATTERNS:
            if pattern.search(text):
                return True
        return False

    def _build_crisis_response(self) -> str:
        return (
            "我先陪着你。你现在的感受很重要，也值得被认真对待。\n\n"
            "看起来你正处在非常难受的状态，这时候我们先不讨论热量补偿。"
            "请先做两件小事：\n"
            "1. 先补一点水，坐下来做 3 次缓慢深呼吸。\n"
            "2. 立刻联系你信任的人，告诉对方你现在很难受，需要陪伴。\n\n"
            "如果你出现持续的自伤或极端节食冲动，请尽快联系当地专业医疗/心理支持资源。"
            "你的安全比任何饮食计划都更重要。"
        )

    def _build_tool_whitelist(self, user_id: Optional[str]) -> list[str]:
        selected: list[str] = []

        for tool_name in LOCAL_TOOL_ALLOWLIST:
            if AgentHub.get_tool(tool_name, user_id=user_id):
                selected.append(tool_name)

        for tool_name in self._get_whitelisted_mcp_tools(user_id):
            if AgentHub.get_tool(tool_name, user_id=user_id):
                selected.append(tool_name)

        return selected

    def _get_whitelisted_mcp_tools(self, user_id: Optional[str]) -> list[str]:
        if not user_id:
            return []

        try:
            all_tools = AgentHub.list_tools(user_id=user_id)
        except Exception as exc:
            logger.warning("Failed to list tools for mcp whitelist: %s", exc)
            return []

        return [
            tool_name
            for tool_name in all_tools
            if tool_name.startswith("mcp_") and self._is_allowed_mcp_tool(tool_name)
        ]

    def _is_allowed_mcp_tool(self, tool_name: str) -> bool:
        normalized = tool_name.lower()
        return any(keyword in normalized for keyword in MCP_TOOL_KEYWORDS)

    def _build_background(
        self,
        base: Optional[str],
        tool_names: list[str],
    ) -> Optional[str]:
        parts = []
        if base:
            parts.append(base)

        tools_line = ", ".join(tool_names) if tool_names else "无"
        policy = (
            "## 执行策略\n"
            "- 你在本轮由主 Agent 手动选择调用，不要改变触发机制。\n"
            "- 若用户表达吃多后的内疚/焦虑，优先先安抚，再给当天可执行方案。\n"
            "- 当需要预算调整时，先使用 diet_analysis.get_today_budget，必要时调用 "
            "diet_analysis.adjust_today_budget。\n"
            f"- 单日临时调整上限由工具硬约束为 +{DAILY_ADJUSTMENT_CAP} kcal，"
            "禁止建议极端补偿行为。\n"
            "- 若工具不可用，直接给出无需工具的安抚与小步行动建议。\n"
            f"- 本轮可用工具白名单：{tools_line}。"
        )
        parts.append(policy)

        return "\n\n".join(parts) if parts else None


def create_emotion_support() -> EmotionSupportSubagent:
    """创建默认配置的情感安抚专家 Subagent。"""
    config = EmotionSupportSubagent.get_default_config()
    return EmotionSupportSubagent(config)


__all__ = [
    "EmotionSupportSubagent",
    "create_emotion_support",
    "EMOTION_SUPPORT_SYSTEM_PROMPT",
]
