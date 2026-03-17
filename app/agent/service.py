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
from datetime import date
from typing import Any, AsyncGenerator, Optional

from app.agent.agents import BaseAgent
from app.agent.context import AgentContextBuilder, AgentContextCompressor
from app.agent.database.repository import AgentRepository, agent_repository
from app.agent.registry import AgentHub
from app.agent.prompts import VISION_ANALYSIS_PROMPT_TEMPLATE
from app.agent.service_executor import AgentExecutionState, stream_agent_execution
from app.agent.service_cards import (
    build_meal_log_confirm_action,
    build_meal_plan_planmode_action,
)
from app.agent.service_collab import (
    build_collab_runtime,
    build_collab_timeline_payload,
    build_collab_trace_step,
    finalize_collab_stages,
    update_collab_stage,
)
from app.agent.service_intents import (
    calculate_nutrition_totals,
    extract_log_items_from_vision_analysis,
    extract_simple_food_items_from_text,
    format_nutrition_totals_text,
    infer_meal_type_for_log,
    is_diet_log_query,
    is_diet_nutrition_query,
    is_meal_plan_query,
)
from app.agent.service_sse import (
    DEFAULT_TRUNCATE_THRESHOLD,
    format_sse_event,
    truncate_value,
)
from app.agent.service_persistence import (
    build_user_image_trace,
    compute_durations_ms,
    persist_tool_events,
)
from app.agent.types import AgentContext

logger = logging.getLogger(__name__)


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
            if is_meal_plan_query(message):
                now = time.time()
                thinking_end_time = now

                trace_steps: list[dict[str, Any]] = []
                planmode_action = build_meal_plan_planmode_action(
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
                thinking_ms, answer_ms = compute_durations_ms(
                    thinking_start_time=thinking_start_time,
                    thinking_end_time=thinking_end_time,
                    answer_end_time=answer_end_time,
                )
                yield self._format_event(
                    "done",
                    {
                        "session_id": actual_session_id,
                        "thinking_duration_ms": thinking_ms,
                        "answer_duration_ms": answer_ms,
                    },
                )

                # Save user + assistant messages (avoid any questionnaire long text).
                processed_images = None
                if images:
                    try:
                        processed_images = await self.context_builder._process_images(
                            images
                        )
                    except Exception as exc:
                        logger.warning(f"Failed to process images for planmode: {exc}")
                        processed_images = None
                user_trace = build_user_image_trace(processed_images)

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
                    thinking_duration_ms=thinking_ms,
                    answer_duration_ms=answer_ms,
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

            state = AgentExecutionState(
                thinking_start_time=thinking_start_time,
                collab_runtime=build_collab_runtime(
                    context.collab_plan,
                    actual_session_id,
                ),
            )

            if state.collab_runtime:
                initial_timeline = build_collab_timeline_payload(state.collab_runtime)
                state.trace_steps.append(
                    build_collab_trace_step(
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
                    state.tool_events.append(
                        {
                            "type": "tool_call",
                            "id": vision_tool_call_id,
                            "name": "vision_analysis",
                            "arguments": {
                                "image_count": len(context.images or []),
                            },
                        }
                    )
                    state.tool_events.append(
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
                    if state.collab_runtime:
                        update_collab_stage(
                            state.collab_runtime,
                            stage_id="recognition",
                            status="completed",
                            summary=(
                                vision_result.get("description")
                                if isinstance(vision_result, dict)
                                else None
                            ),
                        )
                        recognition_timeline = build_collab_timeline_payload(
                            state.collab_runtime
                        )
                        state.trace_steps.append(
                            build_collab_trace_step(
                                content=recognition_timeline,
                                action="collab_timeline",
                            )
                        )
                        yield self._format_event(
                            "collab_timeline",
                            recognition_timeline,
                        )

            # Diet log confirm card-first:
            # When user intent looks like "record this meal" (or they provided food images
            # that the vision step parsed into items), emit a UI confirmation card and
            # avoid claiming data was recorded without a deterministic write path.
            diet_log_query_triggered = is_diet_log_query(context.current_message)
            nutrition_query_triggered = is_diet_nutrition_query(context.current_message)
            vision_items = extract_log_items_from_vision_analysis(context.vision_analysis)
            should_offer_log_confirm = (
                bool(vision_items) or diet_log_query_triggered or nutrition_query_triggered
            )

            items_to_confirm: list[dict[str, Any]] = []
            suggested_meal_type: Optional[str] = None

            if vision_items:
                items_to_confirm = vision_items
                if isinstance(context.vision_analysis, dict):
                    raw_type = context.vision_analysis.get("meal_type")
                    suggested_meal_type = str(raw_type).strip().lower() if raw_type else None
            elif diet_log_query_triggered or nutrition_query_triggered:
                try:
                    from app.diet.service import diet_service

                    parsed = await diet_service.parse_diet_input(
                        user_id=str(user_id),
                        text=context.current_message,
                        images=context.images,
                    )
                    if isinstance(parsed, dict):
                        raw_type = parsed.get("meal_type")
                        suggested_meal_type = str(raw_type).strip().lower() if raw_type else None
                        parsed_items = parsed.get("items")
                        if isinstance(parsed_items, list):
                            for item in parsed_items:
                                if not isinstance(item, dict):
                                    continue
                                food_name = str(item.get("food_name") or "").strip()
                                if not food_name:
                                    continue
                                items_to_confirm.append(
                                    {
                                        "food_name": food_name,
                                        "weight_g": item.get("weight_g"),
                                        "unit": item.get("unit"),
                                        "calories": item.get("calories"),
                                        "protein": item.get("protein"),
                                        "fat": item.get("fat"),
                                        "carbs": item.get("carbs"),
                                    }
                                )
                except Exception as exc:
                    logger.warning("Failed to parse diet input for confirm card: %s", exc)

            if should_offer_log_confirm and not items_to_confirm:
                items_to_confirm = extract_simple_food_items_from_text(context.current_message)

            if should_offer_log_confirm:
                now = time.time()
                if state.thinking_end_time is None:
                    state.thinking_end_time = now

                if state.collab_runtime:
                    finalize_collab_stages(state.collab_runtime)
                    final_timeline = build_collab_timeline_payload(state.collab_runtime)
                    state.trace_steps.append(
                        build_collab_trace_step(
                            content=final_timeline,
                            action="collab_timeline",
                        )
                    )
                    yield self._format_event("collab_timeline", final_timeline)

                inferred_meal_type = infer_meal_type_for_log(suggested_meal_type)

                # Guardrail: avoid creating "empty nutrition" logs.
                can_show_confirm_card = bool(items_to_confirm)
                has_any_quantity = False
                totals: dict[str, float | None] | None = None
                has_any_nutrition = False
                missing_reason: str | None = None

                if can_show_confirm_card:
                    for item in items_to_confirm:
                        if not isinstance(item, dict):
                            continue
                        if item.get("weight_g") is not None:
                            has_any_quantity = True
                            break
                        unit_text = str(item.get("unit") or "").strip()
                        if unit_text:
                            has_any_quantity = True
                            break

                    totals = calculate_nutrition_totals(items_to_confirm)
                    has_any_nutrition = any(
                        totals.get(field) is not None for field in ("calories", "protein", "fat", "carbs")
                    )

                    if not has_any_nutrition:
                        can_show_confirm_card = False
                        missing_reason = "nutrition"
                    elif diet_log_query_triggered and not vision_items and not has_any_quantity:
                        can_show_confirm_card = False
                        missing_reason = "quantity"

                if can_show_confirm_card:
                    confirm_action = build_meal_log_confirm_action(
                        session_id=actual_session_id,
                        suggested_log_date=date.today().isoformat(),
                        suggested_meal_type=inferred_meal_type,
                        items=items_to_confirm,
                    )
                    state.trace_steps.append(
                        {
                            "error": None,
                            "action": "ui_action",
                            "content": confirm_action,
                            "iteration": 0,
                            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                            "source": "agent",
                        }
                    )
                    yield self._format_event(
                        "ui_action",
                        {
                            **confirm_action,
                            "iteration": 0,
                            "source": "agent",
                            "session_id": actual_session_id,
                        },
                    )

                    include_kj = bool(
                        re.search(
                            r"(千焦|kj|焦耳)",
                            context.current_message,
                            re.IGNORECASE,
                        )
                    )
                    if totals is None:
                        totals = calculate_nutrition_totals(items_to_confirm)
                    totals_text = format_nutrition_totals_text(totals, include_kj=include_kj)

                    answer_prefix = "按你提供的分量估算：" if nutrition_query_triggered else "本餐估算："
                    answer_line = f"{answer_prefix}{totals_text}"

                    meal_label = {
                        "breakfast": "早餐",
                        "lunch": "午餐",
                        "dinner": "晚餐",
                        "snack": "加餐",
                    }.get(inferred_meal_type, "这餐")

                    follow_up = (
                        f"这是你今天的{meal_label}吗？"
                        "要不要我帮你记入饮食管理？"
                        "确认后点下方卡片“记录本餐”才会写入（你也可以在卡片里改日期/餐次）。"
                    )

                    intro = f"{answer_line}\n\n{follow_up}"
                else:
                    if items_to_confirm and missing_reason in {"nutrition", "quantity"}:
                        intro = (
                            "我可以帮你记录到饮食管理，但为了避免出现“记录后没有 kcal/PFC”的空记录，"
                            "我需要你再补充一点信息。\n\n"
                            "请补充：食物的**分量**（克/毫升/个/份/碗等），必要时再补充更具体名称（例如：鸡胸肉/鸡腿/带皮与否、做法）。\n"
                            "示例：`鸡胸肉 200g`、`米饭 1 碗`、`鸡蛋 2 个`。\n\n"
                            "你补充后我会立刻生成“确认记录本餐”卡片，让你一键写入。"
                        )
                    elif nutrition_query_triggered:
                        intro = (
                            "我可以帮你估算热量/宏量并生成可记录卡片，但我还缺少可解析的食物明细。\n\n"
                            "你补充一句「吃了什么 + 分量」（例如：鸡胸肉 100g / 米饭 1 碗 / 鸡蛋 2 个），"
                            "我就会给你热量估算并让你一键记入饮食管理。"
                        )
                    else:
                        intro = (
                            "我可以帮你把它记录到饮食管理，但我还没识别到可写入的食物明细。\n\n"
                            "你补充一句「吃了什么 + 大概分量」，我会再生成确认卡片让你一键写入。"
                        )

                state.response_content = intro
                yield self._format_event("text", {"content": intro})

                state.answer_end_time = time.time()
                thinking_ms, answer_ms = compute_durations_ms(
                    thinking_start_time=thinking_start_time,
                    thinking_end_time=state.thinking_end_time,
                    answer_end_time=state.answer_end_time,
                )
                yield self._format_event(
                    "done",
                    {
                        "session_id": actual_session_id,
                        "thinking_duration_ms": thinking_ms,
                        "answer_duration_ms": answer_ms,
                    },
                )

                await self.repository.save_message(
                    actual_session_id,
                    "user",
                    message,
                    trace=build_user_image_trace(context.images),
                )
                await persist_tool_events(self.repository, actual_session_id, state.tool_events)
                await self.repository.save_message(
                    actual_session_id,
                    "assistant",
                    state.response_content,
                    trace=state.trace_steps if state.trace_steps else None,
                    thinking_duration_ms=thinking_ms,
                    answer_duration_ms=answer_ms,
                )

                asyncio.create_task(
                    self.context_compressor.maybe_compress(
                        actual_session_id,
                        self.repository,
                        user_id,
                    )
                )
                return

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

            async for event in stream_agent_execution(
                agent_generator,
                state=state,
                format_event=self._format_event,
                session_id=actual_session_id,
            ):
                yield event

            if state.answer_end_time is None:
                state.answer_end_time = time.time()

            # Build user message content (keep original message, don't append vision analysis)
            user_message_content = message

            await self.repository.save_message(
                actual_session_id,
                "user",
                user_message_content,
                trace=build_user_image_trace(context.images),
            )
            await persist_tool_events(self.repository, actual_session_id, state.tool_events)

            thinking_ms, answer_ms = compute_durations_ms(
                thinking_start_time=thinking_start_time,
                thinking_end_time=state.thinking_end_time,
                answer_end_time=state.answer_end_time,
            )
            await self.repository.save_message(
                actual_session_id,
                "assistant",
                state.response_content,
                trace=state.trace_steps if state.trace_steps else None,
                thinking_duration_ms=thinking_ms,
                answer_duration_ms=answer_ms,
            )

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


    # Helper methods moved to dedicated modules to keep AgentService focused.
    # - app.agent.service_collab
    # - app.agent.service_intents
    # - app.agent.service_cards


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
        return [truncate_value(msg.to_dict(), truncate_threshold) for msg in messages]

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
        return format_sse_event(event_type, data, truncate_threshold)


# 单例
agent_service = AgentService()
