"""
Agent service persistence helpers.

These helpers keep `AgentService.chat()` focused on orchestration while
reusing the exact same persistence semantics across "short-circuit" paths
(PlanMode, diet-log confirm) and the normal agent loop.
"""

from __future__ import annotations

import json
from typing import Any, Optional


def build_user_image_trace(images: Optional[list[dict[str, Any]]]) -> Optional[list[dict[str, Any]]]:
    """Build a stable JSON trace payload for user-uploaded images."""
    if not images:
        return None

    image_sources: list[dict[str, Any]] = []
    for img in images:
        if not isinstance(img, dict):
            continue
        url = img.get("url")
        if not url:
            continue
        image_sources.append(
            {
                "type": "image",
                "url": url,
                "display_url": img.get("display_url"),
                "thumb_url": img.get("thumb_url"),
            }
        )

    return image_sources or None


async def persist_tool_events(
    repository: Any,
    session_id: str,
    tool_events: list[dict[str, Any]],
) -> None:
    """
    Persist tool call/result events into the agent message store.

    This mirrors the frontend-friendly storage model:
    - assistant message with `tool_calls` for each tool invocation
    - tool message for tool results
    """
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
            await repository.save_message(
                session_id,
                "assistant",
                "",
                tool_calls=tool_calls,
            )
            continue

        if event.get("type") == "tool_result":
            if event.get("success"):
                result_content = json.dumps(
                    event.get("result"),
                    ensure_ascii=False,
                    default=str,
                )
            else:
                result_content = f"Error: {event.get('error') or 'Unknown error'}"
            await repository.save_message(
                session_id,
                "tool",
                result_content,
                tool_call_id=event.get("tool_call_id"),
                tool_name=event.get("name"),
            )


def compute_durations_ms(
    *,
    thinking_start_time: float,
    thinking_end_time: Optional[float],
    answer_end_time: float,
) -> tuple[int, int]:
    """
    Compute thinking/answer durations (ms) using the same semantics as AgentService:
    - thinking = from start until first content chunk (or the whole time if no content)
    - answer = from first content until done
    """
    if thinking_end_time is not None:
        thinking_ms = int((thinking_end_time - thinking_start_time) * 1000)
        answer_ms = (
            int((answer_end_time - thinking_end_time) * 1000)
            if answer_end_time > thinking_end_time
            else 0
        )
        return thinking_ms, answer_ms

    thinking_ms = int((answer_end_time - thinking_start_time) * 1000)
    return thinking_ms, 0

