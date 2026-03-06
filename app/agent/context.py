"""
Agent 上下文组装

简化版上下文组装，不包含 RAG 和 Web Search。
"""

import json
import logging
import re
from typing import Optional

from app.agent.types import AgentContext, AgentConfig
from app.agent.database.repository import AgentRepository
from app.agent.database.models import AgentSessionModel
from app.agent.registry import AgentHub
from app.services.user_service import user_service
from app.agent.prompts import (
    USER_ID_PROMPT_TEMPLATE,
    COMPRESS_SYSTEM_PROMPT,
    COMPRESS_USER_PROMPT_TEMPLATE,
)

logger = logging.getLogger(__name__)

FORCE_EMOTION_SUBAGENT_PATTERNS = [
    re.compile(
        r"(内疚|愧疚|自责|后悔|焦虑|难受|难过|低落|抑郁|沮丧|崩溃|压力大|烦躁|压抑|心慌|胸闷|喘不过气)",
        re.IGNORECASE,
    ),
]

WEEKLY_PROGRESS_PATTERNS = [
    re.compile(r"(本周|这周|周进度|周总结|周报|周执行)", re.IGNORECASE),
    re.compile(r"(查看|看看|帮我看|分析).*(进度|完成度|偏差|执行)", re.IGNORECASE),
]

PLANNER_SUBAGENT_TOOL = "subagent_diet_planner"
EMOTION_SUBAGENT_TOOL = "subagent_emotion_support"


class AgentContextBuilder:
    """
    Agent 上下文构建器。

    负责组装 Agent 执行所需的完整上下文。
    """

    def __init__(
        self,
        repository: Optional[AgentRepository] = None,
        recent_messages_limit: int = 20,
    ):
        """
        初始化构建器。

        Args:
            repository: Agent 仓库实例
            recent_messages_limit: 近期消息数量限制
        """
        from app.agent.database.repository import agent_repository

        self.repository = repository or agent_repository
        self.recent_messages_limit = recent_messages_limit

    async def build(
        self,
        session: AgentSessionModel,
        current_message: str,
        user_id: str,
        agent_name: str = "default",
        selected_tools: Optional[list[str]] = None,
        images: Optional[list[dict]] = None,
    ) -> AgentContext:
        """
        构建 Agent 上下文。

        Args:
            session: Agent Session 模型
            current_message: 当前用户消息
            user_id: 用户 ID
            agent_name: Agent 名称（用于选择 Agent 配置）
            selected_tools: 用户选择的工具列表（为空则使用 Agent 默认工具）
            images: 用户上传的图片列表 [{data, mime_type}]

        Returns:
            完整的 Agent 上下文
        """
        session_id = str(session.id)

        # 1. 获取 Agent 配置
        try:
            config = AgentHub.get_agent_config(agent_name)
        except KeyError:
            logger.warning(f"Agent {agent_name} not found, using default config")
            config = AgentConfig(
                name=agent_name,
                description="Default agent",
                system_prompt="You are a helpful assistant.",
            )
        system_prompt = config.system_prompt

        # 2. 获取历史摘要
        (
            compressed_summary,
            compressed_count,
        ) = await self.repository.get_compressed_summary(session_id)

        # 3. 获取近期消息（跳过已压缩的）
        recent_messages = await self.repository.get_recent_messages(
            session_id,
            skip=compressed_count,
            limit=self.recent_messages_limit,
        )

        # 4. 获取可用 Tool schemas
        # Use selected_tools if provided, otherwise get all available tools
        # 传入 user_id 以支持 Subagent Tools
        tools_to_use = selected_tools
        if user_id:
            from app.services.subagent_service import subagent_service

            await subagent_service.sync_user_subagents(user_id)
        available_tools = AgentHub.get_tool_schemas(tools_to_use, user_id=user_id)
        available_tool_names: list[str] = []
        for tool in available_tools:
            if not isinstance(tool, dict):
                continue
            name = tool.get("function", {}).get("name")
            if isinstance(name, str) and name:
                available_tool_names.append(name)
        force_tool_name: Optional[str] = None
        force_tool_arguments: Optional[dict[str, str]] = None
        collab_plan = self._build_collab_plan(
            current_message=current_message,
            available_tool_names=available_tool_names,
            has_images=bool(images),
        )

        if collab_plan and collab_plan.get("force_tool_calls"):
            system_prompt = (
                f"{system_prompt}\n\n"
                "## 本轮多 Agent 协作编排（确定性）\n"
                "- 系统会按固定优先级串行执行已勾选的专业子代理（识别→规划→共情）。\n"
                "- 你需要在最终回答中总结每个阶段结论，并给出下一步建议。\n"
                "- 不要要求用户理解工具细节，重点突出可执行动作。"
            )
        elif (
            self._should_force_emotion_subagent(current_message)
            and EMOTION_SUBAGENT_TOOL in available_tool_names
        ):
            available_tools = AgentHub.get_tool_schemas(
                [EMOTION_SUBAGENT_TOOL],
                user_id=user_id,
            )
            system_prompt = (
                f"{system_prompt}\n\n"
                "## 本轮强制执行策略\n"
                "- 检测到用户明显负面情绪，本轮必须先调用 `subagent_emotion_support`。\n"
                "- 拿到子代理结果后再给最终答复，禁止直接跳过工具。\n"
                "- 若工具不可用，才允许给保底安抚建议。"
            )
            force_tool_name = EMOTION_SUBAGENT_TOOL
            force_tool_arguments = {
                "task": current_message,
                "background": "检测到明显负面情绪，请优先安抚，并执行预算调整交互流程。",
            }

        # 5. user_profile user_instruction
        user_profile = None
        user_instruction = None
        if user_id:
            user_data = await user_service.get_user_by_id(user_id)
            if user_data:
                user_profile = user_data.profile
                user_instruction = user_data.user_instruction

        # 6. Process images if provided
        processed_images = None
        if images:
            processed_images = await self._process_images(images)

        return AgentContext(
            system_prompt=system_prompt,
            user_id=session.user_id,
            session_id=session_id,
            user_profile=user_profile,
            user_instruction=user_instruction,
            history_summary=compressed_summary,
            recent_messages=recent_messages,
            available_tools=available_tools,
            force_tool_name=force_tool_name,
            force_tool_arguments=force_tool_arguments,
            force_tool_calls=(
                collab_plan.get("force_tool_calls")
                if isinstance(collab_plan, dict)
                else None
            ),
            collab_plan=collab_plan,
            current_message=current_message,
            images=processed_images,
        )

    def _should_force_emotion_subagent(self, message: str) -> bool:
        if not message:
            return False
        return any(pattern.search(message) for pattern in FORCE_EMOTION_SUBAGENT_PATTERNS)

    def _is_weekly_progress_query(self, message: str) -> bool:
        if not message:
            return False
        return any(pattern.search(message) for pattern in WEEKLY_PROGRESS_PATTERNS)

    def _build_collab_plan(
        self,
        *,
        current_message: str,
        available_tool_names: list[str],
        has_images: bool,
    ) -> Optional[dict]:
        if not available_tool_names:
            return None

        selected_subagents = [
            name for name in available_tool_names if name.startswith("subagent_")
        ]
        emotion_triggered = self._should_force_emotion_subagent(current_message)
        weekly_progress_triggered = self._is_weekly_progress_query(current_message)

        if not selected_subagents and not weekly_progress_triggered:
            return None

        planner_selected = PLANNER_SUBAGENT_TOOL in available_tool_names
        emotion_selected = EMOTION_SUBAGENT_TOOL in available_tool_names
        custom_selected = sorted(
            [
                name
                for name in selected_subagents
                if name not in {PLANNER_SUBAGENT_TOOL, EMOTION_SUBAGENT_TOOL}
            ]
        )

        stages: list[dict[str, str]] = []
        forced_calls: list[dict[str, object]] = []

        stages.append(
            {
                "id": "recognition",
                "label": "识别",
                "status": "pending" if has_images else "skipped",
                "reason": "" if has_images else "未上传图片，跳过视觉识别",
            }
        )

        if planner_selected:
            stages.append(
                {
                    "id": "planning",
                    "label": "规划",
                    "status": "pending",
                    "reason": "",
                }
            )
            forced_calls.append(
                {
                    "stage_id": "planning",
                    "name": PLANNER_SUBAGENT_TOOL,
                    "arguments": {
                        "task": current_message,
                        "background": "请重点给出下一餐可执行的纠偏建议。",
                    },
                }
            )
        else:
            stages.append(
                {
                    "id": "planning",
                    "label": "规划",
                    "status": "skipped",
                    "reason": "未勾选饮食规划 Agent",
                }
            )

        for index, tool_name in enumerate(custom_selected):
            stage_id = f"custom_{index + 1}"
            stages.append(
                {
                    "id": stage_id,
                    "label": tool_name.replace("subagent_", ""),
                    "status": "pending",
                    "reason": "",
                }
            )
            forced_calls.append(
                {
                    "stage_id": stage_id,
                    "name": tool_name,
                    "arguments": {
                        "task": current_message,
                        "background": "请按你的专业角色补充可执行建议。",
                    },
                }
            )

        weekly_progress_enabled = weekly_progress_triggered and "diet_analysis" in available_tool_names
        if weekly_progress_enabled:
            stages.append(
                {
                    "id": "weekly_progress",
                    "label": "周进度",
                    "status": "pending",
                    "reason": "",
                }
            )
            forced_calls.extend(
                [
                    {
                        "stage_id": "weekly_progress",
                        "name": "diet_analysis",
                        "arguments": {"action": "weekly_summary"},
                    },
                    {
                        "stage_id": "weekly_progress",
                        "name": "diet_analysis",
                        "arguments": {"action": "deviation"},
                    },
                ]
            )
        elif weekly_progress_triggered:
            stages.append(
                {
                    "id": "weekly_progress",
                    "label": "周进度",
                    "status": "skipped",
                    "reason": "未启用 diet_analysis 工具",
                }
            )

        emotion_enabled = emotion_selected and emotion_triggered
        if emotion_enabled:
            stages.append(
                {
                    "id": "emotion",
                    "label": "共情",
                    "status": "pending",
                    "reason": "",
                }
            )
            forced_calls.append(
                {
                    "stage_id": "emotion",
                    "name": EMOTION_SUBAGENT_TOOL,
                    "arguments": {
                        "task": current_message,
                        "background": "先安抚再建议，保持非责备语气。",
                    },
                }
            )
        elif emotion_selected:
            stages.append(
                {
                    "id": "emotion",
                    "label": "共情",
                    "status": "skipped",
                    "reason": "未触发负面情绪语义，跳过共情阶段",
                }
            )
        else:
            stages.append(
                {
                    "id": "emotion",
                    "label": "共情",
                    "status": "skipped",
                    "reason": "未勾选情感安抚 Agent",
                }
            )

        if not forced_calls and not has_images:
            return None

        return {
            "enabled": True,
            "stages": stages,
            "force_tool_calls": forced_calls,
            "emotion_triggered": emotion_triggered,
            "weekly_progress_triggered": weekly_progress_triggered,
        }

    async def _process_images(self, images: list[dict]) -> list[dict]:
        """
        Process images by uploading to imgbb for persistent URLs.

        Args:
            images: List of images [{data, mime_type}]

        Returns:
            List of processed images [{data, mime_type, url}]
        """
        from app.utils.image_storage import upload_to_imgbb

        processed = []
        for img in images:
            result = {
                "data": img["data"],
                "mime_type": img["mime_type"],
                "url": None,
            }

            # Upload to imgbb for persistent URL
            try:
                upload_result = await upload_to_imgbb(
                    img["data"],
                    img["mime_type"],
                )
                if upload_result:
                    result["url"] = upload_result.get("url")
                    result["display_url"] = upload_result.get("display_url")
                    result["thumb_url"] = upload_result.get("thumb_url")
            except Exception as e:
                logger.warning(f"Failed to upload image to imgbb: {e}")

            processed.append(result)

        return processed

    def build_messages(self, context: AgentContext) -> list[dict]:
        """
        从上下文构建 LLM 输入消息列表。

        Args:
            context: Agent 上下文

        Returns:
            消息列表（符合 OpenAI 格式）
        """
        messages = []

        # 1. System prompt（含用户画像和指令）
        system_content = context.system_prompt

        if context.user_id:
            system_content += USER_ID_PROMPT_TEMPLATE.format(user_id=context.user_id)

        if context.user_profile:
            system_content += f"\n\n## 用户画像\n{context.user_profile}"

        if context.user_instruction:
            system_content += f"\n\n## 用户指令\n{context.user_instruction}"

        messages.append({"role": "system", "content": system_content})

        # 2. 历史摘要
        if context.history_summary:
            messages.append(
                {
                    "role": "system",
                    "content": f"## 历史对话摘要\n{context.history_summary}",
                }
            )

        # 3. 近期消息
        messages.extend(context.recent_messages)

        # 4. 当前消息（可能包含图片）
        if context.images:
            # Build multimodal content with images
            content_parts = []
            content_parts.append(
                {
                    "type": "text",
                    "text": context.current_message,
                }
            )

            # Add image content
            for img in context.images:
                if img.get("url"):
                    # Use imgbb URL
                    content_parts.append(
                        {"type": "image_url", "image_url": {"url": img["url"]}}
                    )

            messages.append({"role": "user", "content": content_parts})
        else:
            # Plain text message
            messages.append({"role": "user", "content": context.current_message})

        if context.vision_analysis and context.vision_tool_call_id:
            tool_call = {
                "id": context.vision_tool_call_id,
                "type": "function",
                "function": {
                    "name": "vision_analysis",
                    "arguments": json.dumps(
                        {"image_count": len(context.images or [])},
                        ensure_ascii=False,
                    ),
                },
            }
            messages.append(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [tool_call],
                }
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": context.vision_tool_call_id,
                    "name": "vision_analysis",
                    "content": json.dumps(
                        context.vision_analysis,
                        ensure_ascii=False,
                        default=str,
                    ),
                }
            )

        return messages


class AgentContextCompressor:
    """
    Agent 上下文压缩器。

    负责压缩历史消息为摘要。
    """

    def __init__(
        self,
        compression_threshold: int = 10,
        recent_messages_limit: int = 20,
    ):
        """
        初始化压缩器。

        Args:
            compression_threshold: 触发压缩的消息数阈值
            recent_messages_limit: 保留的未压缩消息数
        """
        self.compression_threshold = compression_threshold
        self.recent_messages_limit = recent_messages_limit

    async def maybe_compress(
        self,
        session_id: str,
        repository: AgentRepository,
        user_id: Optional[str] = None,
    ) -> bool:
        """
        检查并执行压缩（如需要）。

        Args:
            session_id: Session ID
            repository: Agent 仓库
            user_id: 用户 ID（用于 LLM 上下文）

        Returns:
            是否执行了压缩
        """
        from app.llm.provider import LLMProvider
        from app.llm.context import llm_context
        from app.config import settings

        provider = LLMProvider(settings.llm)

        # 获取当前状态
        total_count = await repository.get_message_count(session_id)
        compressed_summary, compressed_count = await repository.get_compressed_summary(
            session_id
        )

        uncompressed_count = total_count - compressed_count

        # 检查是否需要压缩
        if uncompressed_count < self.compression_threshold + self.recent_messages_limit:
            return False

        # 获取需要压缩的消息
        messages_to_compress = await repository.get_recent_messages(
            session_id,
            skip=compressed_count,
            limit=self.compression_threshold,
        )

        if not messages_to_compress:
            return False

        # 构建压缩提示
        messages_text = "\n".join(
            [f"{msg['role']}: {msg['content']}" for msg in messages_to_compress]
        )

        previous_summary = (
            f"之前的摘要：{compressed_summary}" if compressed_summary else ""
        )
        prompt = COMPRESS_USER_PROMPT_TEMPLATE.format(
            messages_text=messages_text,
            previous_summary=previous_summary,
        )

        # 调用 LLM 生成摘要
        try:
            invoker = provider.create_invoker(llm_type="fast")

            with llm_context("agent:compressor", user_id, session_id):
                response = await invoker.ainvoke(
                    [
                        {
                            "role": "system",
                            "content": COMPRESS_SYSTEM_PROMPT,
                        },
                        {"role": "user", "content": prompt},
                    ]
                )

            new_summary = response.content
            new_count = compressed_count + len(messages_to_compress)

            # 更新数据库
            await repository.update_compressed_summary(
                session_id,
                new_summary,
                new_count,
            )

            logger.info(
                f"Compressed {len(messages_to_compress)} messages for session {session_id}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to compress context: {e}")
            return False


# 单例
agent_context_builder = AgentContextBuilder()
agent_context_compressor = AgentContextCompressor()
