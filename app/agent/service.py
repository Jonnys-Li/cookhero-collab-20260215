"""
AgentService - Agent 模块的主入口

职责单一：组装上下文 → 交给 Agent 执行
"""
from __future__ import annotations
import asyncio
import json
import logging
import re
import time
import uuid
from datetime import date, timedelta
from dataclasses import asdict
from typing import Any, AsyncGenerator, Optional

# 默认截断阈值（字符数）
DEFAULT_TRUNCATE_THRESHOLD = 500
TRUNCATE_SUFFIX = "...[truncated]"

from app.agent.types import AgentChunk, AgentChunkType, AgentContext
from app.agent.agents import BaseAgent
from app.agent.context import AgentContextBuilder, AgentContextCompressor
from app.agent.database.repository import AgentRepository, agent_repository
from app.agent.registry import AgentHub
from app.agent.prompts import VISION_ANALYSIS_PROMPT_TEMPLATE

logger = logging.getLogger(__name__)


# 不截断的字段（用户输入和 LLM 输出）
EXCLUDE_TRUNCATE_KEYS = {"content"}

MEAL_PLAN_QUERY_PATTERNS = [
    re.compile(
        r"(周计划|周菜单|周食谱|一周|7天|七天|备餐|饮食计划|餐食计划|meal\s*plan|mealprep)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(饮食|餐食|备餐|菜单|食谱|训练).*(计划|规划|安排|制定|生成|推荐|方案)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(计划|规划|安排|制定|生成|推荐|方案).*(饮食|餐食|备餐|菜单|食谱|训练)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(怎么吃|吃什么|如何备餐).*(一周|7天|七天|计划|方案)",
        re.IGNORECASE,
    ),
]


def _truncate_value(
    value: Any,
    threshold: int = DEFAULT_TRUNCATE_THRESHOLD,
    exclude_keys: Optional[set[str]] = None,
    _current_key: Optional[str] = None,
) -> Any:
    """
    递归截断值中的字符串字段。

    Args:
        value: 任意值
        threshold: 字符串截断阈值
        exclude_keys: 不截断的字段名集合
        _current_key: 当前处理的字段名（内部使用）

    Returns:
        截断后的值
    """
    if exclude_keys is None:
        exclude_keys = EXCLUDE_TRUNCATE_KEYS

    if value is None:
        return None

    if isinstance(value, str):
        # 如果当前字段在排除列表中，不截断
        if _current_key in exclude_keys:
            return value
        if len(value) > threshold:
            return value[:threshold] + TRUNCATE_SUFFIX
        return value

    if isinstance(value, dict):
        return {
            k: _truncate_value(v, threshold, exclude_keys, _current_key=k)
            for k, v in value.items()
        }

    if isinstance(value, list):
        return [
            _truncate_value(item, threshold, exclude_keys, _current_key)
            for item in value
        ]

    # 其他类型（int, float, bool 等）直接返回
    return value


def _sanitize_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {k: _sanitize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    return str(value)


def _build_fallback_agent(name: str) -> BaseAgent:
    from app.agent.agents import DefaultAgent
    from app.agent.types import AgentConfig

    return DefaultAgent(
        AgentConfig(
            name=name,
            description="Default assistant",
            system_prompt="You are a helpful assistant.",
        )
    )


class AgentService:
    """
    Agent 服务层。

    职责：
    1. 管理 Session 生命周期
    2. 组装上下文
    3. 调用 Agent 执行
    4. 保存消息和轨迹
    """

    def __init__(
        self,
        repository: Optional[AgentRepository] = None,
    ):
        """
        初始化服务。

        Args:
            repository: Agent 仓库
        """
        self.repository = repository or agent_repository
        self.context_builder = AgentContextBuilder(repository=self.repository)
        self.context_compressor = AgentContextCompressor()

    async def chat(
        self,
        session_id: Optional[str],
        user_id: str,
        message: str,
        agent_name: str = "default",
        streaming: bool = False,
        selected_tools: Optional[list[str]] = None,
        images: Optional[list[dict]] = None,
    ) -> AsyncGenerator[str, None]:
        """
        主入口：与 Agent 对话。

        Args:
            session_id: Session ID（可选，为空则创建新 Session）
            user_id: 用户 ID
            message: 用户消息
            agent_name: Agent 名称（用于选择 Agent，不存储在 Session 中）
            streaming: 是否启用流式输出
            selected_tools: 用户选择的工具列表（为空则使用默认工具）
            images: 用户上传的图片列表 [{data, mime_type}]

        Yields:
            SSE 格式的事件字符串
        """
        from app.llm.provider import LLMProvider
        from app.config import settings

        provider = LLMProvider(settings.llm)

        # Start timing
        thinking_start_time = time.time()
        thinking_end_time: Optional[float] = None
        answer_end_time: Optional[float] = None

        try:
            # 1. 获取或创建 Session（不再传入 agent_name）
            session = await self.repository.get_or_create_session(session_id, user_id)
            actual_session_id = str(session.id)

            # 2. 发送 session 信息
            yield self._format_event(
                "session",
                {
                    "session_id": actual_session_id,
                    "title": session.title,
                },
            )

            # ==========================================================================
            # PlanMode card-first: early short-circuit for meal-plan intent.
            #
            # This MUST happen before building context or invoking the agent loop to
            # avoid multi-iteration LLM output (which can look like duplicated
            # questionnaires for plan requests).
            # ==========================================================================
            if self._is_meal_plan_query(message):
                now = time.time()
                thinking_end_time = now

                trace_steps: list[dict[str, Any]] = []
                planmode_action = self._build_meal_plan_planmode_action(
                    runtime=None,
                    session_id=actual_session_id,
                )

                trace_steps.append(
                    {
                        "error": None,
                        "action": "ui_action",
                        "content": planmode_action,
                        "iteration": 0,
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                        "source": "subagent",
                        "subagent_name": "diet_planner",
                    }
                )
                yield self._format_event(
                    "ui_action",
                    {
                        **planmode_action,
                        "iteration": 0,
                        "source": "subagent",
                        "subagent_name": "diet_planner",
                        "session_id": actual_session_id,
                    },
                )

                intro = "我用 PlanMode 给你生成一周饮食计划，我们用卡片一步步完成。"
                response_content = intro
                yield self._format_event("text", {"content": intro})

                answer_end_time = time.time()
                yield self._format_event(
                    "done",
                    {
                        "session_id": actual_session_id,
                        "thinking_duration_ms": int(
                            (thinking_end_time - thinking_start_time) * 1000
                        ),
                        "answer_duration_ms": int(
                            (answer_end_time - thinking_end_time) * 1000
                        ),
                    },
                )

                # Save user + assistant messages (avoid any questionnaire long text).
                user_trace = None
                if images:
                    try:
                        processed_images = await self.context_builder._process_images(images)
                    except Exception as exc:
                        logger.warning(f"Failed to process images for planmode: {exc}")
                        processed_images = None
                    if processed_images:
                        image_sources = []
                        for img in processed_images:
                            if img.get("url"):
                                image_sources.append(
                                    {
                                        "type": "image",
                                        "url": img.get("url"),
                                        "display_url": img.get("display_url"),
                                        "thumb_url": img.get("thumb_url"),
                                    }
                                )
                        if image_sources:
                            user_trace = image_sources

                await self.repository.save_message(
                    actual_session_id,
                    "user",
                    message,
                    trace=user_trace,
                )
                await self.repository.save_message(
                    actual_session_id,
                    "assistant",
                    response_content,
                    trace=trace_steps if trace_steps else None,
                    thinking_duration_ms=int(
                        (thinking_end_time - thinking_start_time) * 1000
                    ),
                    answer_duration_ms=int(
                        (answer_end_time - thinking_end_time) * 1000
                    ),
                )

                # Compress in background (non-blocking).
                asyncio.create_task(
                    self.context_compressor.maybe_compress(
                        actual_session_id,
                        self.repository,
                        user_id,
                    )
                )
                return

            # 3. 组装上下文
            context = await self.context_builder.build(
                session,
                message,
                user_id,
                agent_name=agent_name,
                selected_tools=selected_tools,
                images=images,
            )

            response_content = ""
            trace_steps: list[dict[str, Any]] = []
            tool_events = []
            collab_runtime = self._build_collab_runtime(
                context.collab_plan,
                actual_session_id,
            )
            planmode_query_triggered = self._is_meal_plan_query(context.current_message)
            if collab_runtime:
                initial_timeline = self._build_collab_timeline_payload(collab_runtime)
                trace_steps.append(
                    self._build_collab_trace_step(
                        content=initial_timeline,
                        action="collab_timeline",
                    )
                )
                yield self._format_event("collab_timeline", initial_timeline)

            # 4. If images present, run vision analysis and emit event
            if context.images:
                vision_result = await self._analyze_images(context)
                if vision_result:
                    vision_tool_call_id = f"vision-{uuid.uuid4().hex}"
                    context.vision_analysis = vision_result
                    context.vision_tool_call_id = vision_tool_call_id
                    tool_events.append(
                        {
                            "type": "tool_call",
                            "id": vision_tool_call_id,
                            "name": "vision_analysis",
                            "arguments": {
                                "image_count": len(context.images or []),
                            },
                        }
                    )
                    tool_events.append(
                        {
                            "type": "tool_result",
                            "tool_call_id": vision_tool_call_id,
                            "name": "vision_analysis",
                            "success": True,
                            "result": vision_result,
                            "error": None,
                        }
                    )
                    yield self._format_event("vision", vision_result)
                    if collab_runtime:
                        self._update_collab_stage(
                            collab_runtime,
                            stage_id="recognition",
                            status="completed",
                            summary=(
                                vision_result.get("description")
                                if isinstance(vision_result, dict)
                                else None
                            ),
                        )
                        recognition_timeline = self._build_collab_timeline_payload(
                            collab_runtime
                        )
                        trace_steps.append(
                            self._build_collab_trace_step(
                                content=recognition_timeline,
                                action="collab_timeline",
                            )
                        )
                        yield self._format_event(
                            "collab_timeline",
                            recognition_timeline,
                        )

            # PlanMode card-first: for meal-plan intent, return a wizard card immediately
            # without invoking the main LLM pipeline (demo stability + lower latency).
            if planmode_query_triggered:
                now = time.time()
                if thinking_end_time is None:
                    thinking_end_time = now

                if collab_runtime:
                    self._finalize_collab_stages(collab_runtime)
                    final_timeline = self._build_collab_timeline_payload(collab_runtime)
                    trace_steps.append(
                        self._build_collab_trace_step(
                            content=final_timeline,
                            action="collab_timeline",
                        )
                    )
                    yield self._format_event("collab_timeline", final_timeline)

                planmode_action = self._build_meal_plan_planmode_action(
                    runtime=collab_runtime,
                    session_id=actual_session_id,
                )
                trace_steps.append(
                    {
                        "error": None,
                        "action": "ui_action",
                        "content": planmode_action,
                        "iteration": 0,
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                        "source": "subagent",
                        "subagent_name": "diet_planner",
                    }
                )
                yield self._format_event(
                    "ui_action",
                    {
                        **planmode_action,
                        "iteration": 0,
                        "source": "subagent",
                        "subagent_name": "diet_planner",
                        "session_id": actual_session_id,
                    },
                )

                intro = "我用 PlanMode 给你生成一周饮食计划，我们用卡片一步步完成。"
                response_content = intro
                yield self._format_event("text", {"content": intro})

                answer_end_time = time.time()
                yield self._format_event(
                    "done",
                    {
                        "session_id": actual_session_id,
                        "thinking_duration_ms": int(
                            (thinking_end_time - thinking_start_time) * 1000
                        ),
                        "answer_duration_ms": int(
                            (answer_end_time - thinking_end_time) * 1000
                        ),
                    },
                )

            else:
                # 5. 获取 Agent
                agent = self._get_agent_or_fallback(agent_name)

                # 6. 创建 LLM invoker
                invoker = provider.create_invoker(
                    llm_type="fast",
                    streaming=streaming,
                )

                # 7. 执行 Agent
                if streaming:
                    agent_generator = agent.run_streaming(invoker, context)
                else:
                    agent_generator = agent.run(invoker, context)

                async for chunk in agent_generator:
                    # 处理不同类型的 chunk
                    if chunk.type == AgentChunkType.CONTENT:
                        # Track thinking end and answer start times on first content
                        if thinking_end_time is None:
                            thinking_end_time = time.time()
                        response_content += chunk.data
                        yield self._format_event(
                            "text",
                            {
                                "content": chunk.data,
                            },
                        )

                    elif chunk.type == AgentChunkType.TOOL_CALL:
                        tool_call = chunk.data
                        # Calculate iteration number
                        iteration = len(
                            [t for t in trace_steps if t.get("action") == "tool_call"]
                        )
                        tool_events.append(
                            {
                                "type": "tool_call",
                                "id": tool_call.id,
                                "name": tool_call.name,
                                "arguments": tool_call.arguments,
                            }
                        )
                        # Store tool call in trace
                        trace_steps.append(
                            {
                                "error": None,
                                "action": "tool_call",
                                "content": None,
                                "iteration": iteration,
                                "timestamp": chunk.data.id
                                if hasattr(chunk.data, "id")
                                else None,
                                "tool_calls": [
                                    {
                                        "name": tool_call.name,
                                        "arguments": tool_call.arguments,
                                    }
                                ],
                            }
                        )
                        yield self._format_event(
                            "tool_call",
                            {
                                "id": tool_call.id,
                                "name": tool_call.name,
                                "arguments": tool_call.arguments,
                                "iteration": iteration,
                            },
                        )
                        if collab_runtime:
                            forced_call = collab_runtime["forced_call_map"].get(tool_call.id)
                            if forced_call:
                                stage_id = str(forced_call.get("stage_id") or "")
                                if stage_id:
                                    self._update_collab_stage(
                                        collab_runtime,
                                        stage_id=stage_id,
                                        status="running",
                                    )
                                    timeline_payload = self._build_collab_timeline_payload(
                                        collab_runtime
                                    )
                                    trace_steps.append(
                                        self._build_collab_trace_step(
                                            content=timeline_payload,
                                            action="collab_timeline",
                                        )
                                    )
                                    yield self._format_event(
                                        "collab_timeline",
                                        timeline_payload,
                                    )

                    elif chunk.type == AgentChunkType.TOOL_RESULT:
                        result = chunk.data
                        # Calculate iteration number
                        iteration = len(
                            [t for t in trace_steps if t.get("action") == "tool_result"]
                        )
                        tool_events.append(
                            {
                                "type": "tool_result",
                                "tool_call_id": result.tool_call_id,
                                "name": result.name,
                                "success": result.success,
                                "result": result.result,
                                "error": result.error,
                            }
                        )
                        # Store tool result in trace
                        trace_steps.append(
                            {
                                "error": result.error if not result.success else None,
                                "action": "tool_result",
                                "content": result.result,
                                "iteration": iteration,
                                "timestamp": None,
                                "tool_calls": [
                                    {
                                        "name": result.name,
                                        "arguments": {},
                                    }
                                ],
                            }
                        )
                        yield self._format_event(
                            "tool_result",
                            {
                                "name": result.name,
                                "success": result.success,
                                "result": result.result,
                                "error": result.error,
                                "iteration": iteration,
                            },
                        )
                        if collab_runtime:
                            forced_call = collab_runtime["forced_call_map"].get(
                                result.tool_call_id
                            )
                            if forced_call:
                                stage_id = str(forced_call.get("stage_id") or "")
                                if stage_id:
                                    stage_success = bool(result.success)
                                    self._record_collab_tool_output(
                                        collab_runtime,
                                        stage_id=stage_id,
                                        tool_name=result.name,
                                        arguments=forced_call.get("arguments"),
                                        result=result.result,
                                        success=stage_success,
                                    )
                                    expected_count = collab_runtime["stage_expected"].get(
                                        stage_id, 1
                                    )
                                    completed_count = collab_runtime["stage_completed"].get(
                                        stage_id, 0
                                    )
                                    if stage_success:
                                        completed_count += 1
                                        collab_runtime["stage_completed"][
                                            stage_id
                                        ] = completed_count
                                    next_status = (
                                        "completed"
                                        if stage_success and completed_count >= expected_count
                                        else "failed"
                                        if not stage_success
                                        else "running"
                                    )
                                    summary = (
                                        self._build_result_summary(result.result)
                                        if stage_success
                                        else (result.error or "执行失败")
                                    )
                                    self._update_collab_stage(
                                        collab_runtime,
                                        stage_id=stage_id,
                                        status=next_status,
                                        summary=summary,
                                    )
                                    timeline_payload = self._build_collab_timeline_payload(
                                        collab_runtime
                                    )
                                    trace_steps.append(
                                        self._build_collab_trace_step(
                                            content=timeline_payload,
                                            action="collab_timeline",
                                        )
                                    )
                                    yield self._format_event(
                                        "collab_timeline",
                                        timeline_payload,
                                    )

                    elif chunk.type == AgentChunkType.TRACE:
                        trace_step = chunk.data
                        trace_dict = asdict(trace_step)
                        trace_steps.append(trace_dict)
                        if trace_dict.get("action") == "ui_action":
                            ui_payload = trace_dict.get("content")
                            if isinstance(ui_payload, dict):
                                yield self._format_event(
                                    "ui_action",
                                    {
                                        **ui_payload,
                                        "iteration": trace_dict.get("iteration", 0),
                                        "source": trace_dict.get("source"),
                                        "subagent_name": trace_dict.get("subagent_name"),
                                        "session_id": actual_session_id,
                                    },
                                )
                        yield self._format_event("trace", trace_dict)

                    elif chunk.type == AgentChunkType.UI_ACTION:
                        action_payload = chunk.data if isinstance(chunk.data, dict) else {}
                        yield self._format_event(
                            "ui_action",
                            {
                                **action_payload,
                                "session_id": actual_session_id,
                            },
                        )

                    elif chunk.type == AgentChunkType.ERROR:
                        yield self._format_event("error", chunk.data)

                    elif chunk.type == AgentChunkType.DONE:
                        # Track answer end time
                        answer_end_time = time.time()

                        if collab_runtime:
                            self._finalize_collab_stages(collab_runtime)
                            final_timeline = self._build_collab_timeline_payload(
                                collab_runtime
                            )
                            trace_steps.append(
                                self._build_collab_trace_step(
                                    content=final_timeline,
                                    action="collab_timeline",
                                )
                            )
                            yield self._format_event("collab_timeline", final_timeline)

                        ui_action_payload: Optional[dict[str, Any]] = None
                        if planmode_query_triggered:
                            ui_action_payload = self._build_meal_plan_planmode_action(
                                runtime=collab_runtime,
                                session_id=actual_session_id,
                            )
                        elif collab_runtime and self._should_emit_smart_recommendation_card(
                            collab_runtime
                        ):
                            ui_action_payload = self._build_smart_recommendation_action(
                                collab_runtime
                            )

                        if ui_action_payload:
                            ui_action_subagent = (
                                "diet_planner"
                                if planmode_query_triggered
                                else "emotion_support"
                            )
                            trace_steps.append(
                                {
                                    "error": None,
                                    "action": "ui_action",
                                    "content": ui_action_payload,
                                    "iteration": 0,
                                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                    "source": "subagent",
                                    "subagent_name": ui_action_subagent,
                                }
                            )
                            yield self._format_event(
                                "ui_action",
                                {
                                    **ui_action_payload,
                                    "iteration": 0,
                                    "source": "subagent",
                                    "subagent_name": ui_action_subagent,
                                    "session_id": actual_session_id,
                                },
                            )

                        if not response_content and collab_runtime:
                            fallback_content = self._build_collab_fallback_content(
                                collab_runtime,
                                include_smart_card=bool(
                                    isinstance(ui_action_payload, dict)
                                    and ui_action_payload.get("action_type")
                                    == "smart_recommendation_card"
                                ),
                            )
                            if fallback_content:
                                if thinking_end_time is None:
                                    thinking_end_time = time.time()
                                response_content = fallback_content
                                yield self._format_event(
                                    "text",
                                    {
                                        "content": fallback_content,
                                    },
                                )

                        # Calculate durations
                        thinking_duration_ms = None
                        answer_duration_ms = None

                        # For Agent: thinking = all time before first CONTENT
                        # If there was CONTENT, thinking = start to first CONTENT, answer = first CONTENT to end
                        # If no CONTENT, all time is thinking
                        if thinking_end_time is not None:
                            thinking_duration_ms = int(
                                (thinking_end_time - thinking_start_time) * 1000
                            )
                            answer_duration_ms = (
                                int((answer_end_time - thinking_end_time) * 1000)
                                if answer_end_time > thinking_end_time
                                else 0
                            )
                        else:
                            thinking_duration_ms = int(
                                (answer_end_time - thinking_start_time) * 1000
                            )

                        yield self._format_event(
                            "done",
                            {
                                "session_id": actual_session_id,
                                "thinking_duration_ms": thinking_duration_ms,
                                "answer_duration_ms": answer_duration_ms,
                                **chunk.data,
                            },
                        )

            # 8. 保存消息（所有执行过程都存储在 trace 中）
            # Calculate final timing if not already done
            if answer_end_time is None:
                answer_end_time = time.time()

            # Build user message content (keep original message, don't append vision analysis)
            user_message_content = message

            # Build trace with image URLs for user message
            user_trace = None
            if context.images:
                image_sources = []
                for img in context.images:
                    if img.get("url"):
                        image_sources.append({
                            "type": "image",
                            "url": img.get("url"),
                            "display_url": img.get("display_url"),
                            "thumb_url": img.get("thumb_url"),
                        })
                if image_sources:
                    user_trace = image_sources

            # 保存用户消息
            await self.repository.save_message(
                actual_session_id,
                "user",
                user_message_content,
                trace=user_trace,
            )

            for event in tool_events:
                if event.get("type") == "tool_call":
                    tool_calls = [
                        {
                            "id": event.get("id") or "",
                            "type": "function",
                            "function": {
                                "name": event.get("name") or "",
                                "arguments": json.dumps(
                                    event.get("arguments") or {},
                                    ensure_ascii=False,
                                    default=str,
                                ),
                            },
                        }
                    ]
                    await self.repository.save_message(
                        actual_session_id,
                        "assistant",
                        "",
                        tool_calls=tool_calls,
                    )
                elif event.get("type") == "tool_result":
                    if event.get("success"):
                        result_content = json.dumps(
                            event.get("result"),
                            ensure_ascii=False,
                            default=str,
                        )
                    else:
                        result_content = f"Error: {event.get('error') or 'Unknown error'}"
                    await self.repository.save_message(
                        actual_session_id,
                        "tool",
                        result_content,
                        tool_call_id=event.get("tool_call_id"),
                        tool_name=event.get("name"),
                    )

            final_thinking_ms = None
            final_answer_ms = None
            if thinking_end_time is not None:
                final_thinking_ms = int(
                    (thinking_end_time - thinking_start_time) * 1000
                )
                final_answer_ms = (
                    int((answer_end_time - thinking_end_time) * 1000)
                    if answer_end_time > thinking_end_time
                    else 0
                )
            else:
                final_thinking_ms = int((answer_end_time - thinking_start_time) * 1000)

            await self.repository.save_message(
                actual_session_id,
                "assistant",
                response_content,
                trace=trace_steps if trace_steps else None,
                thinking_duration_ms=final_thinking_ms,
                answer_duration_ms=final_answer_ms,
            )

            # 8. 后台压缩上下文
            asyncio.create_task(
                self.context_compressor.maybe_compress(
                    actual_session_id,
                    self.repository,
                    user_id,
                )
            )

        except Exception as e:
            logger.exception(f"AgentService.chat failed: {e}")
            yield self._format_event("error", {"error": str(e)})

    def _build_collab_runtime(
        self,
        collab_plan: Optional[dict[str, Any]],
        session_id: str,
    ) -> Optional[dict[str, Any]]:
        if not isinstance(collab_plan, dict):
            return None
        if not collab_plan.get("enabled"):
            return None

        raw_stages = collab_plan.get("stages") or []
        if not isinstance(raw_stages, list):
            raw_stages = []
        stages: list[dict[str, Any]] = []
        for stage in raw_stages:
            if not isinstance(stage, dict):
                continue
            stage_id = str(stage.get("id") or "").strip()
            if not stage_id:
                continue
            stages.append(
                {
                    "id": stage_id,
                    "label": str(stage.get("label") or stage_id),
                    "status": str(stage.get("status") or "pending"),
                    "reason": str(stage.get("reason") or ""),
                    "summary": str(stage.get("summary") or ""),
                }
            )

        force_tool_calls = collab_plan.get("force_tool_calls") or []
        if not isinstance(force_tool_calls, list):
            force_tool_calls = []
        forced_call_map: dict[str, dict[str, Any]] = {}
        stage_expected: dict[str, int] = {}
        for index, raw_call in enumerate(force_tool_calls):
            if not isinstance(raw_call, dict):
                continue
            name = str(raw_call.get("name") or "").strip()
            if not name:
                continue
            stage_id = str(raw_call.get("stage_id") or "").strip()
            forced_id = f"forced-{name}-{index}"
            forced_call_map[forced_id] = raw_call
            if stage_id:
                stage_expected[stage_id] = stage_expected.get(stage_id, 0) + 1

        return {
            "session_id": session_id,
            "timeline_id": f"collab-{uuid.uuid4().hex}",
            "stages": stages,
            "forced_call_map": forced_call_map,
            "stage_expected": stage_expected,
            "stage_completed": {},
            "stage_outputs": {},
            "weekly_summary": None,
            "weekly_deviation": None,
            "emotion_triggered": bool(collab_plan.get("emotion_triggered")),
            "weekly_progress_triggered": bool(
                collab_plan.get("weekly_progress_triggered")
            ),
            "planning_triggered": bool(collab_plan.get("planning_triggered")),
        }

    def _build_collab_timeline_payload(self, runtime: dict[str, Any]) -> dict[str, Any]:
        return {
            "action_id": runtime.get("timeline_id"),
            "action_type": "collab_timeline",
            "source": "collaboration_pipeline",
            "stages": runtime.get("stages", []),
        }

    def _build_collab_trace_step(
        self,
        *,
        content: dict[str, Any],
        action: str,
    ) -> dict[str, Any]:
        return {
            "error": None,
            "action": action,
            "content": content,
            "iteration": 0,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "source": "agent",
            "subagent_name": None,
        }

    def _update_collab_stage(
        self,
        runtime: dict[str, Any],
        *,
        stage_id: str,
        status: str,
        summary: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> None:
        for stage in runtime.get("stages", []):
            if stage.get("id") != stage_id:
                continue
            stage["status"] = status
            if summary is not None:
                stage["summary"] = summary
            if reason is not None:
                stage["reason"] = reason
            return

    def _record_collab_tool_output(
        self,
        runtime: dict[str, Any],
        *,
        stage_id: str,
        tool_name: str,
        arguments: Any,
        result: Any,
        success: bool,
    ) -> None:
        stage_outputs = runtime.setdefault("stage_outputs", {})
        existing = stage_outputs.setdefault(stage_id, [])
        existing.append(
            {
                "tool_name": tool_name,
                "arguments": arguments if isinstance(arguments, dict) else {},
                "result": result,
                "success": success,
            }
        )

        if tool_name != "diet_analysis":
            return
        if not isinstance(arguments, dict):
            return
        action = str(arguments.get("action") or "").strip()
        payload = self._normalize_result_payload(result)
        if not isinstance(payload, dict):
            return
        if action == "weekly_summary":
            runtime["weekly_summary"] = payload.get("summary", payload)
        elif action == "deviation":
            runtime["weekly_deviation"] = payload.get("analysis", payload)

    def _normalize_result_payload(self, result: Any) -> Any:
        if isinstance(result, dict):
            return result
        if isinstance(result, str):
            try:
                return json.loads(result)
            except json.JSONDecodeError:
                return result
        return result

    def _build_result_summary(self, result: Any) -> str:
        payload = self._normalize_result_payload(result)
        if isinstance(payload, dict):
            for key in ("message", "result", "summary"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()[:120]
            if "analysis" in payload and isinstance(payload["analysis"], dict):
                analysis = payload["analysis"]
                total_dev = analysis.get("total_deviation")
                exec_rate = analysis.get("execution_rate")
                return (
                    f"偏差 {total_dev} kcal，执行率 {exec_rate}%"
                    if total_dev is not None and exec_rate is not None
                    else "已生成周偏差分析"
                )
            return "已返回结构化结果"
        text = str(payload or "").strip()
        if not text:
            return "执行完成"
        return text[:120]

    def _finalize_collab_stages(self, runtime: dict[str, Any]) -> None:
        for stage in runtime.get("stages", []):
            status = stage.get("status")
            if status in {"completed", "failed", "skipped"}:
                continue
            if status == "running":
                stage["status"] = "completed"
                if not stage.get("summary"):
                    stage["summary"] = "执行完成"
            else:
                stage["status"] = "skipped"
                if not stage.get("reason"):
                    stage["reason"] = "本轮未触发该阶段"

    def _build_collab_fallback_content(
        self,
        runtime: dict[str, Any],
        *,
        include_smart_card: bool = True,
    ) -> str:
        lines = ["我已经按你勾选的 Agent 跑完一轮协作，整理如下："]
        for stage in runtime.get("stages", []):
            label = stage.get("label") or stage.get("id")
            status = stage.get("status")
            if status == "completed":
                summary = stage.get("summary") or "已完成"
                lines.append(f"- {label}：✅ {summary}")
            elif status == "failed":
                summary = stage.get("summary") or stage.get("reason") or "执行失败"
                lines.append(f"- {label}：⚠️ {summary}")
            elif status == "skipped":
                reason = stage.get("reason") or "未触发"
                lines.append(f"- {label}：⏭️ {reason}")
        if include_smart_card:
            lines.append("\n你可以直接在下方推荐卡里选择“立即应用”来落地到饮食管理。")
        else:
            lines.append(
                "\n如果你希望我给出下一餐纠偏建议，可以直接说“帮我纠偏下一餐”。"
            )
        return "\n".join(lines)

    def _is_meal_plan_query(self, message: str) -> bool:
        if not message:
            return False
        return any(pattern.search(message) for pattern in MEAL_PLAN_QUERY_PATTERNS)

    def _infer_planmode_default_intensity(
        self,
        runtime: Optional[dict[str, Any]],
    ) -> str:
        if not isinstance(runtime, dict):
            return "balanced"
        weekly_deviation = runtime.get("weekly_deviation")
        if not isinstance(weekly_deviation, dict):
            return "balanced"
        try:
            total_deviation = int(weekly_deviation.get("total_deviation"))
        except (TypeError, ValueError):
            return "balanced"
        if total_deviation >= 1200:
            return "conservative"
        if total_deviation <= 300:
            return "aggressive"
        return "balanced"

    def _build_meal_plan_planmode_action(
        self,
        *,
        runtime: Optional[dict[str, Any]],
        session_id: str,
    ) -> dict[str, Any]:
        default_intensity = self._infer_planmode_default_intensity(runtime)
        return {
            "action_id": f"meal-plan-planmode-{uuid.uuid4().hex}",
            "action_type": "meal_plan_planmode_card",
            "title": "先做 4 步个性化配置，再生成你的周计划",
            "description": "按步骤选择饮食与训练偏好，生成可预览、可确认写入的一周方案。",
            "timeout_seconds": 10,
            "timeout_mode": "timeout_suggest_only",
            "default_timeout_suggestion": "超时后仅保留建议，不会自动写入饮食数据。",
            "steps": [
                {
                    "id": "goal_food",
                    "title": "饮食目标与食物类型",
                    "hint": "选择你的主要目标和偏好的食物类型。",
                },
                {
                    "id": "restriction",
                    "title": "限制与过敏",
                    "hint": "填写需要避开的食物或过敏原。",
                },
                {
                    "id": "relax",
                    "title": "放松场景方式",
                    "hint": "选择你更容易执行的放松方式。",
                },
                {
                    "id": "weekly_intensity",
                    "title": "周进度强度与训练偏好",
                    "hint": "选择下周计划强度和训练偏好。",
                },
            ],
            "goal_options": [
                {"value": "fat_loss", "label": "减脂"},
                {"value": "muscle_gain", "label": "增肌"},
                {"value": "maintenance", "label": "维持体重"},
                {"value": "recovery", "label": "恢复与减压"},
            ],
            "food_type_options": [
                {"value": "chinese_home", "label": "家常中餐"},
                {"value": "high_protein", "label": "高蛋白"},
                {"value": "low_carb", "label": "低碳水"},
                {"value": "light_meal", "label": "轻食"},
                {"value": "comfort_food", "label": "安抚型食物"},
            ],
            "restriction_options": [
                {"value": "no_spicy", "label": "少辣"},
                {"value": "low_fat", "label": "低脂"},
                {"value": "vegetarian", "label": "素食优先"},
                {"value": "no_lactose", "label": "低乳糖"},
                {"value": "low_sodium", "label": "低钠"},
            ],
            "relax_mode_options": [
                {"value": "breathing", "label": "呼吸放松"},
                {"value": "walk", "label": "散步舒展"},
                {"value": "journaling", "label": "情绪记录"},
                {"value": "music", "label": "音乐放松"},
            ],
            "weekly_intensity_options": [
                {"value": "conservative", "label": "保守"},
                {"value": "balanced", "label": "平衡"},
                {"value": "aggressive", "label": "积极"},
            ],
            "training_focus_options": [
                {"value": "low_impact", "label": "低冲击"},
                {"value": "strength", "label": "力量提升"},
                {"value": "cardio", "label": "有氧耐力"},
                {"value": "mobility", "label": "灵活拉伸"},
            ],
            "defaults": {
                "goal": "fat_loss",
                "weekly_intensity": default_intensity,
                "training_focus": "low_impact",
                "cook_time_minutes": 30,
                "training_minutes_per_day": 25,
                "training_days_per_week": 3,
            },
            "source": "planmode_pipeline",
            "session_id": session_id,
        }

    def _infer_next_meal_plan(self) -> tuple[date, str]:
        now = time.localtime()
        today = date.today()
        hour = now.tm_hour
        if hour < 10:
            return today, "lunch"
        if hour < 15:
            return today, "dinner"
        if hour < 21:
            return today, "snack"
        return today + timedelta(days=1), "breakfast"

    def _should_emit_smart_recommendation_card(self, runtime: dict[str, Any]) -> bool:
        """
        Smart recommendation card is an *optional* UI enhancement.

        We only auto-emit it when the user's intent is likely about:
        - planning/correction (纠偏/下一餐/怎么吃)
        - emotion support
        - weekly progress review

        For pure factual/calculation queries (e.g., calories lookup), do not emit
        the card to avoid "answering the wrong question".
        """
        if not isinstance(runtime, dict):
            return False
        return bool(
            runtime.get("planning_triggered")
            or runtime.get("emotion_triggered")
            or runtime.get("weekly_progress_triggered")
        )

    def _build_smart_recommendation_action(
        self,
        runtime: dict[str, Any],
    ) -> dict[str, Any]:
        plan_date, meal_type = self._infer_next_meal_plan()
        weekly_summary = runtime.get("weekly_summary") if isinstance(runtime, dict) else None
        weekly_deviation = runtime.get("weekly_deviation") if isinstance(runtime, dict) else None
        execution_rate = None
        total_deviation = None
        if isinstance(weekly_deviation, dict):
            execution_rate = weekly_deviation.get("execution_rate")
            total_deviation = weekly_deviation.get("total_deviation")
            try:
                execution_rate = (
                    float(execution_rate) if execution_rate is not None else None
                )
            except (TypeError, ValueError):
                execution_rate = None
            try:
                total_deviation = (
                    int(total_deviation) if total_deviation is not None else None
                )
            except (TypeError, ValueError):
                total_deviation = None

        weekly_text = "你可以说“看本周进度”获取执行摘要。"
        if execution_rate is not None and total_deviation is not None:
            weekly_text = (
                f"本周执行率 {execution_rate:.1f}% ，总偏差 {total_deviation} kcal。"
            )
        elif isinstance(weekly_summary, dict):
            avg_daily = weekly_summary.get("avg_daily_calories")
            if avg_daily is not None:
                weekly_text = f"本周日均摄入约 {avg_daily:.0f} kcal。"

        return {
            "action_id": f"smart-recommendation-{uuid.uuid4().hex}",
            "action_type": "smart_recommendation_card",
            "title": "我整理了一个可直接执行的智能推荐卡",
            "description": "包含下一餐纠偏、放松场景建议和周进度入口。",
            "timeout_seconds": 10,
            "timeout_mode": "timeout_suggest_only",
            "default_timeout_suggestion": "若你暂时不点击，我会保留建议，不会自动写入饮食数据。",
            "next_meal_options": [
                {
                    "option_id": "balanced",
                    "title": "轻负担均衡餐",
                    "description": "优先蛋白 + 蔬菜，减少高油高糖负担。",
                    "meal_type": meal_type,
                    "plan_date": plan_date.isoformat(),
                    "dish_name": "鸡蛋豆腐蔬菜碗",
                    "calories": 420,
                },
                {
                    "option_id": "protein",
                    "title": "高蛋白稳态餐",
                    "description": "帮助稳定饱腹感，避免再次冲动进食。",
                    "meal_type": meal_type,
                    "plan_date": plan_date.isoformat(),
                    "dish_name": "鸡胸肉沙拉配酸奶",
                    "calories": 460,
                },
                {
                    "option_id": "comfort",
                    "title": "温和安抚餐",
                    "description": "低负担 + 情绪安抚，避免惩罚性节食。",
                    "meal_type": meal_type,
                    "plan_date": plan_date.isoformat(),
                    "dish_name": "燕麦酸奶水果杯",
                    "calories": 380,
                },
            ],
            "relax_suggestions": [
                "做 3 轮方块呼吸（吸4秒-停4秒-呼4秒-停4秒）。",
                "走到窗边或户外 5 分钟，放松肩颈和下颌。",
                "给自己一句中性提醒：一次波动不等于失败。",
            ],
            "weekly_progress": {
                "trigger_hint": "看本周进度",
                "summary_text": weekly_text,
                "execution_rate": execution_rate,
                "total_deviation": total_deviation,
            },
            "budget_options": [50, 100, 150],
            "source": "collaboration_pipeline",
            "session_id": runtime.get("session_id"),
        }

    def _get_agent_or_fallback(self, agent_name: str) -> BaseAgent:
        try:
            return AgentHub.get_agent(agent_name)
        except KeyError:
            logger.warning(f"Agent {agent_name} not found, using fallback")
            return _build_fallback_agent("default")

    async def _analyze_images(self, context: AgentContext) -> Optional[dict]:
        """
        Analyze images using the vision provider.

        Args:
            context: Agent context with images

        Returns:
            Vision analysis result dict, or None if analysis fails
        """
        if not context.images:
            return None

        try:
            from app.vision.provider import vision_provider, ImageInput

            # Check if vision is enabled
            if not vision_provider.is_enabled:
                logger.warning("Vision provider is not enabled, skipping image analysis")
                return None

            # Convert images to ImageInput format
            image_inputs = []
            for img in context.images:
                image_inputs.append(
                    ImageInput.from_base64(img["data"], img["mime_type"])
                )

            recent_messages = context.recent_messages if context.recent_messages else []
            recent_text = "\n".join(
                [
                    f"{msg.get('role')}: {msg.get('content', '')}"
                    for msg in recent_messages
                ]
            )

            # Build analysis prompt
            prompt = VISION_ANALYSIS_PROMPT_TEMPLATE.format(
                recent_text=recent_text or "无",
                current_message=context.current_message,
            )

            # Run vision analysis
            result_str = await vision_provider.analyze(
                text=prompt,
                images=image_inputs,
                user_id=context.user_id,
                conversation_id=context.session_id,
            )

            # Parse JSON response
            import json
            try:
                result = json.loads(result_str)
                return result
            except json.JSONDecodeError:
                # Return as plain text if not valid JSON
                return {
                    "description": result_str,
                    "is_food_related": False,
                    "confidence": 0.5,
                }

        except Exception as e:
            logger.error(f"Vision analysis failed: {e}", exc_info=True)
            return None

    async def get_session(self, session_id: str) -> Optional[dict]:
        """获取 Session 信息。"""
        session = await self.repository.get_session(session_id)
        if session:
            return session.to_dict()
        return None

    async def list_sessions(
        self,
        user_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        """列出 Sessions。"""
        return await self.repository.list_sessions(
            user_id=user_id,
            limit=limit,
            offset=offset,
        )

    async def delete_session(self, session_id: str) -> bool:
        """删除 Session。"""
        return await self.repository.delete_session(session_id)

    async def update_session_title(self, session_id: str, title: str) -> bool:
        """更新 Session 标题。"""
        return await self.repository.update_session_title(session_id, title)

    async def get_messages(
        self,
        session_id: str,
        limit: Optional[int] = None,
        truncate_threshold: int = DEFAULT_TRUNCATE_THRESHOLD,
    ) -> list[dict]:
        """
        获取 Session 的消息历史。

        Args:
            session_id: Session ID
            limit: 返回消息数量限制
            truncate_threshold: 截断阈值

        Returns:
            截断后的消息列表
        """
        messages = await self.repository.get_messages(session_id, limit)
        # 对每条消息的内容进行截断
        return [_truncate_value(msg.to_dict(), truncate_threshold) for msg in messages]

    def _format_event(
        self,
        event_type: str,
        data: dict,
        truncate_threshold: int = DEFAULT_TRUNCATE_THRESHOLD,
    ) -> str:
        """
        格式化 SSE 事件。

        Args:
            event_type: 事件类型
            data: 事件数据
            truncate_threshold: 截断阈值

        Returns:
            SSE 格式字符串
        """
        # 截断数据中的字符串字段
        truncated_data = _truncate_value(data, truncate_threshold)
        safe_data = _sanitize_value(truncated_data)
        payload = {"type": event_type, **safe_data}
        return f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


# 单例
agent_service = AgentService()
