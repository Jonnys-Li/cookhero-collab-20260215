# app/agent/subagents/builtin/emotion_support.py
"""
EmotionSupportSubagent - 情感安抚专家 Subagent

在用户出现饮食内疚、焦虑、自责等场景时，提供支持性反馈与低风险行动建议。
"""

import logging
import re
import uuid
from typing import Awaitable, Callable, Optional

from app.agent.registry import AgentHub
from app.agent.subagents.base import BaseSubagent, SubagentConfig
from app.agent.types import TraceStep, ToolResult
from app.services.emotion_budget_service import emotion_budget_service

logger = logging.getLogger(__name__)


EMOTION_SUPPORT_SYSTEM_PROMPT = """你是 CookHero 的情感安抚专家，目标是在用户因饮食而自责、焦虑或内疚时，提供温和、具体、可执行的支持。

## 核心原则

1. **先安抚后建议**：先认可用户情绪，再提供下一步行动。
2. **不羞辱不评判**：禁止使用带有责备、羞辱或恐吓语气的话术。
3. **小步行动**：优先提供当天可执行的小动作，而不是极端补偿方案。
4. **结果导向**：若调用工具，必须把结果翻译成清晰建议，不要只贴工具结果。

## 预算调整策略（低风险）

- 在用户出现明显负面情绪（尤其是饮食相关的内疚/焦虑/自责）时，可给出“当天预算弹性调整”建议。
- 若用户未明确提到“吃多了”，也可把预算调整作为可选项，不要强推。
- `delta_calories` 使用正整数，建议在 50~150 之间。
- 调整仅针对当天临时预算，不修改长期目标。
- 调用前应优先使用 `diet_analysis.get_today_budget` 获取当前状态。

## 输出要求

- 使用简洁的中文 Markdown。
- 结构建议：`情绪回应` + `今日可执行计划` + `下一步提醒`。
- 回答中不要暴露任何工具调用格式或参数细节。
- 结尾必须用**一句**简短的“二选一”问题收尾（不要再额外抛出第二个问题），例如：
  - “你现在更需要我给你 2-3 个放松方式，还是帮你把今天预算稍微上调一点？”
  - 若下方出现预算调整卡片，可提示“也可以直接点卡片选择 +50/+100/+150”。"""

LOCAL_TOOL_ALLOWLIST = ["datetime", "diet_analysis", "web_search"]
MCP_BUDGET_TOOL_SUFFIXES = (
    "_get_today_budget",
    "_auto_adjust_today_budget",
)
DAILY_ADJUSTMENT_CAP = 150
AUTO_ADJUST_TIMEOUT_SECONDS = 10
AUTO_ADJUST_DEFAULT_DELTA = 100
AUTO_ADJUST_OPTIONS = [50, 100, 150]

CRISIS_PATTERNS = [
    re.compile(r"(不想活|活着没意义|结束生命|自杀|自残)", re.IGNORECASE),
    re.compile(r"(绝食|饿死自己|几天不吃|极端节食)", re.IGNORECASE),
    re.compile(r"(惩罚自己|我不配吃|我很糟糕|讨厌自己)", re.IGNORECASE),
]

NEGATIVE_EMOTION_PATTERNS = [
    re.compile(r"(内疚|愧疚|自责|后悔)", re.IGNORECASE),
    re.compile(
        r"(焦虑|难受|难过|低落|抑郁|沮丧|崩溃|压力大|烦躁|压抑|心慌|胸闷|喘不过气)",
        re.IGNORECASE,
    ),
]

OVEREAT_PATTERNS = [
    re.compile(r"(吃多了|吃太多|吃撑|吃超|暴食|失控吃)", re.IGNORECASE),
    re.compile(r"(热量超标|卡路里超标|摄入过量|超出预算)", re.IGNORECASE),
]

HIGH_INTENSITY_PATTERNS = [
    re.compile(r"(崩溃|绝望|完全失控|特别难受|非常糟糕)", re.IGNORECASE),
]

LOW_INTENSITY_PATTERNS = [
    re.compile(r"(有点|有些|稍微|一点点)", re.IGNORECASE),
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
        llm_tool_names = tool_names

        if user_id and self._should_offer_budget_adjustment(scan_text):
            action_payload = await self._build_budget_ui_action(
                user_id=user_id,
                scan_text=scan_text,
                tool_names=tool_names,
            )
            await self._emit_event(
                event_handler,
                TraceStep(
                    iteration=0,
                    action="ui_action",
                    content=action_payload,
                    source="subagent",
                    subagent_name=self.name,
                ),
            )
            llm_tool_names = self._build_non_budget_toolset(tool_names)
            combined_background = self._build_background(
                self._merge_background(
                    background,
                    self._build_ui_action_background_hint(action_payload),
                ),
                llm_tool_names,
            )

        return await self.run_with_tools(
            task=task,
            user_id=user_id,
            background=combined_background,
            event_handler=event_handler,
            tool_names_override=llm_tool_names,
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
        if tool_name.startswith("mcp_diet_auto_adjust_"):
            return True
        normalized = tool_name.lower()
        return normalized.startswith("mcp_") and normalized.endswith(
            MCP_BUDGET_TOOL_SUFFIXES
        )

    def _build_non_budget_toolset(self, tool_names: list[str]) -> list[str]:
        # If MCP budget tools are available, we hide *all* budget tools from the LLM
        # after emitting the UI card to avoid accidental auto-adjust calls.
        #
        # If MCP tools are NOT available, keep `diet_analysis` so the subagent can
        # still read budget state and explain it (graceful degrade).
        has_mcp_budget_tools = any(
            name.startswith("mcp_") and self._is_budget_tool(name) for name in tool_names
        )
        if not has_mcp_budget_tools:
            return list(tool_names)

        return [tool_name for tool_name in tool_names if not self._is_budget_tool(tool_name)]

    def _is_budget_tool(self, tool_name: str) -> bool:
        normalized = tool_name.lower()
        if tool_name == "diet_analysis":
            return True
        if normalized.endswith("_get_today_budget"):
            return True
        if normalized.endswith("_auto_adjust_today_budget"):
            return True
        return False

    def _should_offer_budget_adjustment(self, text: str) -> bool:
        has_negative = any(pattern.search(text) for pattern in NEGATIVE_EMOTION_PATTERNS)
        if not has_negative:
            return False
        return True

    def _infer_emotion_level(self, text: str) -> str:
        if any(pattern.search(text) for pattern in HIGH_INTENSITY_PATTERNS):
            return "high"
        if any(pattern.search(text) for pattern in LOW_INTENSITY_PATTERNS):
            return "low"
        return "medium"

    async def _build_budget_ui_action(
        self,
        *,
        user_id: str,
        scan_text: str,
        tool_names: list[str],
    ) -> dict:
        can_apply = any(self._is_budget_tool(name) for name in tool_names)
        budget_snapshot = None
        provider = None
        unavailable_reason = None

        if can_apply:
            try:
                budget_result = await emotion_budget_service.get_today_budget(
                    user_id=user_id,
                )
                budget_snapshot = budget_result.get("budget")
                provider = budget_result.get("used_provider")
            except Exception as exc:
                can_apply = False
                unavailable_reason = str(exc)
        else:
            unavailable_reason = "当前未检测到可用预算调整工具"

        emotion_level = self._infer_emotion_level(scan_text)

        options = [
            {
                "label": f"+{delta} kcal",
                "delta_calories": delta,
                "recommended": delta == AUTO_ADJUST_DEFAULT_DELTA,
            }
            for delta in AUTO_ADJUST_OPTIONS
        ]

        return {
            "action_id": f"emotion-budget-{uuid.uuid4().hex}",
            "action_type": "emotion_budget_adjust",
            "title": "我可以帮你温和调整今天的摄入预算",
            "description": "你不需要惩罚自己，我们可以先留出一点弹性空间（需要你确认才会生效）。",
            "emotion_level": emotion_level,
            "options": options,
            "default_delta_calories": AUTO_ADJUST_DEFAULT_DELTA,
            "timeout_seconds": AUTO_ADJUST_TIMEOUT_SECONDS,
            "auto_apply_on_timeout": False,
            "can_apply": can_apply,
            "unavailable_reason": unavailable_reason,
            "budget_snapshot": budget_snapshot,
            "budget_provider": provider,
            "source": "emotion_support",
        }

    def _build_ui_action_background_hint(self, action_payload: dict) -> str:
        budget_snapshot = action_payload.get("budget_snapshot") or {}
        snapshot_line = (
            f"当前有效预算 {budget_snapshot.get('effective_goal')} kcal，"
            f"剩余可调上限 {budget_snapshot.get('remaining_adjustment_cap')} kcal。"
            if isinstance(budget_snapshot, dict) and budget_snapshot
            else "当前预算快照暂不可用。"
        )
        can_apply = bool(action_payload.get("can_apply"))
        capability_line = (
            "本轮已向前端下发预算调整交互卡片（需要用户点击“立即应用”才会生效），"
            "请你不要再次调用预算调整工具，也不要暗示会自动执行。"
            if can_apply
            else "本轮预算自动调整能力暂不可用，请仅做情绪安抚与替代建议。"
        )
        return (
            "## 本轮情绪支持强化策略\n"
            f"- {capability_line}\n"
            f"- {snapshot_line}\n"
            "- 回复结构：先共情 → 给出 2 条小步行动 → 提供 2~3 条放松场景建议 → 最后用一句二选一问题收尾。\n"
            f"- 放松建议模板：\n{self._build_relax_template(action_payload.get('emotion_level'))}"
        )

    def _build_relax_template(self, emotion_level: Optional[str]) -> str:
        if emotion_level == "high":
            return (
                "  1) 先做 4-6 次缓慢呼吸（吸气4秒、呼气6秒）。\n"
                "  2) 去阳台/楼下走 8-10 分钟，感受空气和光线。\n"
                "  3) 选一个轻负担补给：温热牛奶/酸奶+水果。"
            )
        if emotion_level == "low":
            return (
                "  1) 站起来伸展肩颈 2 分钟。\n"
                "  2) 倒一杯温水，慢慢喝完。\n"
                "  3) 给自己一句中性提醒：'一次波动不等于失败。'"
            )
        return (
            "  1) 做 3 轮方块呼吸（吸4秒-停4秒-呼4秒-停4秒）。\n"
            "  2) 走到窗边或户外 5 分钟，放松肩颈。\n"
            "  3) 晚点选择一份高蛋白轻食（如鸡蛋/豆腐/酸奶）。"
        )

    def _merge_background(self, base: Optional[str], extra: Optional[str]) -> Optional[str]:
        if base and extra:
            return f"{base}\n\n{extra}"
        return base or extra

    def _build_background(
        self,
        base: Optional[str],
        tool_names: list[str],
    ) -> Optional[str]:
        parts = []
        if base:
            parts.append(base)

        tools_line = ", ".join(tool_names) if tool_names else "无"
        has_budget_tools = any(self._is_budget_tool(name) for name in tool_names)
        budget_policy_line = (
            "- 当需要预算调整时，优先调用 mcp_diet_auto_adjust_*；若不可用，回退 diet_analysis。\n"
            if has_budget_tools
            else "- 本轮未启用预算工具，请避免承诺已自动调整预算。\n"
        )
        policy = (
            "## 执行策略\n"
            "- 你在本轮由主 Agent 手动选择调用，不要改变触发机制。\n"
            "- 若用户表达明显负面情绪，优先先安抚，再给当天可执行方案。\n"
            f"{budget_policy_line}"
            f"- 单日临时调整上限由工具硬约束为 +{DAILY_ADJUSTMENT_CAP} kcal，"
            "禁止建议极端补偿行为。\n"
            "- 若工具不可用，直接给出无需工具的安抚与小步行动建议。\n"
            "- 回复结构模板：1) 情绪回应（先共情） 2) 今日可执行计划（2条） 3) 下一步提醒（1条）。\n"
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
