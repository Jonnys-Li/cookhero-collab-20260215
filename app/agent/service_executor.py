"""
Agent service execution helpers.

This module extracts the large "consume AgentChunk stream" loop out of
`app.agent.service.AgentService.chat()` so the service stays readable and
future refactors (e.g. smarter tracing, metrics) are localized.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any, AsyncGenerator, Callable, Optional

from app.agent.types import AgentChunk, AgentChunkType
from app.agent.service_persistence import compute_durations_ms


@dataclass
class AgentExecutionState:
    response_content: str = ""
    trace_steps: list[dict[str, Any]] = field(default_factory=list)
    tool_events: list[dict[str, Any]] = field(default_factory=list)

    thinking_start_time: float = 0.0
    thinking_end_time: Optional[float] = None
    answer_end_time: Optional[float] = None

    collab_runtime: Optional[dict[str, Any]] = None


async def stream_agent_execution(
    agent_generator: AsyncGenerator[AgentChunk, None],
    *,
    state: AgentExecutionState,
    format_event: Callable[[str, dict[str, Any]], str],
    session_id: str,
) -> AsyncGenerator[str, None]:
    """
    Consume an agent generator and yield SSE events, updating `state` in-place.
    """
    from app.agent.service_cards import (
        build_smart_recommendation_action,
        should_emit_smart_recommendation_card,
    )
    from app.agent.service_collab import (
        build_collab_fallback_content,
        build_collab_timeline_payload,
        build_collab_trace_step,
        build_result_summary,
        finalize_collab_stages,
        record_collab_tool_output,
        update_collab_stage,
    )

    collab_runtime = state.collab_runtime

    async for chunk in agent_generator:
        if chunk.type == AgentChunkType.CONTENT:
            # First content chunk marks end of "thinking".
            if state.thinking_end_time is None:
                state.thinking_end_time = time.time()

            state.response_content += str(chunk.data)
            yield format_event(
                "text",
                {
                    "content": chunk.data,
                },
            )
            continue

        if chunk.type == AgentChunkType.TOOL_CALL:
            tool_call = chunk.data
            iteration = len([t for t in state.trace_steps if t.get("action") == "tool_call"])

            state.tool_events.append(
                {
                    "type": "tool_call",
                    "id": getattr(tool_call, "id", None),
                    "name": getattr(tool_call, "name", None),
                    "arguments": getattr(tool_call, "arguments", None),
                }
            )

            state.trace_steps.append(
                {
                    "error": None,
                    "action": "tool_call",
                    "content": None,
                    "iteration": iteration,
                    "timestamp": getattr(tool_call, "id", None),
                    "tool_calls": [
                        {
                            "name": getattr(tool_call, "name", None),
                            "arguments": getattr(tool_call, "arguments", None),
                        }
                    ],
                }
            )

            yield format_event(
                "tool_call",
                {
                    "id": getattr(tool_call, "id", None),
                    "name": getattr(tool_call, "name", None),
                    "arguments": getattr(tool_call, "arguments", None),
                    "iteration": iteration,
                },
            )

            if collab_runtime:
                forced_call = collab_runtime["forced_call_map"].get(getattr(tool_call, "id", None))
                if forced_call:
                    stage_id = str(forced_call.get("stage_id") or "")
                    if stage_id:
                        update_collab_stage(
                            collab_runtime,
                            stage_id=stage_id,
                            status="running",
                        )
                        timeline_payload = build_collab_timeline_payload(collab_runtime)
                        state.trace_steps.append(
                            build_collab_trace_step(
                                content=timeline_payload,
                                action="collab_timeline",
                            )
                        )
                        yield format_event("collab_timeline", timeline_payload)

            continue

        if chunk.type == AgentChunkType.TOOL_RESULT:
            result = chunk.data
            iteration = len([t for t in state.trace_steps if t.get("action") == "tool_result"])

            state.tool_events.append(
                {
                    "type": "tool_result",
                    "tool_call_id": getattr(result, "tool_call_id", None),
                    "name": getattr(result, "name", None),
                    "success": getattr(result, "success", None),
                    "result": getattr(result, "result", None),
                    "error": getattr(result, "error", None),
                }
            )

            state.trace_steps.append(
                {
                    "error": getattr(result, "error", None) if not getattr(result, "success", False) else None,
                    "action": "tool_result",
                    "content": getattr(result, "result", None),
                    "iteration": iteration,
                    "timestamp": None,
                    "tool_calls": [
                        {
                            "name": getattr(result, "name", None),
                            "arguments": {},
                        }
                    ],
                }
            )

            yield format_event(
                "tool_result",
                {
                    "name": getattr(result, "name", None),
                    "success": getattr(result, "success", None),
                    "result": getattr(result, "result", None),
                    "error": getattr(result, "error", None),
                    "iteration": iteration,
                },
            )

            if collab_runtime:
                forced_call = collab_runtime["forced_call_map"].get(getattr(result, "tool_call_id", None))
                if forced_call:
                    stage_id = str(forced_call.get("stage_id") or "")
                    if stage_id:
                        stage_success = bool(getattr(result, "success", False))
                        record_collab_tool_output(
                            collab_runtime,
                            stage_id=stage_id,
                            tool_name=str(getattr(result, "name", "")),
                            arguments=forced_call.get("arguments"),
                            result=getattr(result, "result", None),
                            success=stage_success,
                        )
                        expected_count = collab_runtime["stage_expected"].get(stage_id, 1)
                        completed_count = collab_runtime["stage_completed"].get(stage_id, 0)
                        if stage_success:
                            completed_count += 1
                            collab_runtime["stage_completed"][stage_id] = completed_count

                        next_status = (
                            "completed"
                            if stage_success and completed_count >= expected_count
                            else "failed"
                            if not stage_success
                            else "running"
                        )
                        summary = (
                            build_result_summary(getattr(result, "result", None))
                            if stage_success
                            else (getattr(result, "error", None) or "执行失败")
                        )
                        update_collab_stage(
                            collab_runtime,
                            stage_id=stage_id,
                            status=next_status,
                            summary=summary,
                        )
                        timeline_payload = build_collab_timeline_payload(collab_runtime)
                        state.trace_steps.append(
                            build_collab_trace_step(
                                content=timeline_payload,
                                action="collab_timeline",
                            )
                        )
                        yield format_event("collab_timeline", timeline_payload)

            continue

        if chunk.type == AgentChunkType.TRACE:
            trace_step = chunk.data
            trace_dict = asdict(trace_step)
            state.trace_steps.append(trace_dict)

            if trace_dict.get("action") == "ui_action":
                ui_payload = trace_dict.get("content")
                if isinstance(ui_payload, dict):
                    yield format_event(
                        "ui_action",
                        {
                            **ui_payload,
                            "iteration": trace_dict.get("iteration", 0),
                            "source": trace_dict.get("source"),
                            "subagent_name": trace_dict.get("subagent_name"),
                            "session_id": session_id,
                        },
                    )

            yield format_event("trace", trace_dict)
            continue

        if chunk.type == AgentChunkType.UI_ACTION:
            action_payload = chunk.data if isinstance(chunk.data, dict) else {}
            yield format_event(
                "ui_action",
                {
                    **action_payload,
                    "session_id": session_id,
                },
            )
            continue

        if chunk.type == AgentChunkType.ERROR:
            yield format_event("error", chunk.data)
            continue

        if chunk.type == AgentChunkType.DONE:
            state.answer_end_time = time.time()

            if collab_runtime:
                finalize_collab_stages(collab_runtime)
                final_timeline = build_collab_timeline_payload(collab_runtime)
                state.trace_steps.append(
                    build_collab_trace_step(
                        content=final_timeline,
                        action="collab_timeline",
                    )
                )
                yield format_event("collab_timeline", final_timeline)

            ui_action_payload: Optional[dict[str, Any]] = None
            if collab_runtime and should_emit_smart_recommendation_card(collab_runtime):
                ui_action_payload = build_smart_recommendation_action(collab_runtime)

            if ui_action_payload:
                state.trace_steps.append(
                    {
                        "error": None,
                        "action": "ui_action",
                        "content": ui_action_payload,
                        "iteration": 0,
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                        "source": "subagent",
                        "subagent_name": "emotion_support",
                    }
                )
                yield format_event(
                    "ui_action",
                    {
                        **ui_action_payload,
                        "iteration": 0,
                        "source": "subagent",
                        "subagent_name": "emotion_support",
                        "session_id": session_id,
                    },
                )

            if not state.response_content and collab_runtime:
                fallback_content = build_collab_fallback_content(
                    collab_runtime,
                    include_smart_card=bool(
                        isinstance(ui_action_payload, dict)
                        and ui_action_payload.get("action_type") == "smart_recommendation_card"
                    ),
                )
                if fallback_content:
                    if state.thinking_end_time is None:
                        state.thinking_end_time = time.time()
                    state.response_content = fallback_content
                    yield format_event("text", {"content": fallback_content})

            # Emit done with durations.
            assert state.answer_end_time is not None
            thinking_ms, answer_ms = compute_durations_ms(
                thinking_start_time=state.thinking_start_time,
                thinking_end_time=state.thinking_end_time,
                answer_end_time=state.answer_end_time,
            )
            yield format_event(
                "done",
                {
                    "session_id": session_id,
                    "thinking_duration_ms": thinking_ms,
                    "answer_duration_ms": answer_ms,
                    **(chunk.data if isinstance(chunk.data, dict) else {}),
                },
            )
            continue

        # Fallback: unknown chunk types should not crash streaming.
        try:
            yield format_event(
                "trace",
                {
                    "action": "unknown_chunk",
                    "content": json.loads(json.dumps(chunk.data, default=str)),
                    "iteration": 0,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "error": None,
                    "source": "agent",
                    "subagent_name": None,
                },
            )
        except Exception:
            # Absolute last resort: ignore.
            continue

