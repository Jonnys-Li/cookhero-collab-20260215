from __future__ import annotations

import json
import time
import uuid
from typing import Any, Optional


def build_collab_runtime(
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
        "weekly_progress_triggered": bool(collab_plan.get("weekly_progress_triggered")),
        "planning_triggered": bool(collab_plan.get("planning_triggered")),
    }


def build_collab_timeline_payload(runtime: dict[str, Any]) -> dict[str, Any]:
    return {
        "action_id": runtime.get("timeline_id"),
        "action_type": "collab_timeline",
        "source": "collaboration_pipeline",
        "stages": runtime.get("stages", []),
    }


def build_collab_trace_step(*, content: dict[str, Any], action: str) -> dict[str, Any]:
    return {
        "error": None,
        "action": action,
        "content": content,
        "iteration": 0,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": "agent",
        "subagent_name": None,
    }


def update_collab_stage(
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


def record_collab_tool_output(
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
    payload = normalize_result_payload(result)
    if not isinstance(payload, dict):
        return
    if action == "weekly_summary":
        runtime["weekly_summary"] = payload.get("summary", payload)
    elif action == "deviation":
        runtime["weekly_deviation"] = payload.get("analysis", payload)


def normalize_result_payload(result: Any) -> Any:
    if isinstance(result, dict):
        return result
    if isinstance(result, str):
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return result
    return result


def build_result_summary(result: Any) -> str:
    payload = normalize_result_payload(result)
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


def finalize_collab_stages(runtime: dict[str, Any]) -> None:
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


def build_collab_fallback_content(
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
        lines.append("\n如果你希望我给出下一餐纠偏建议，可以直接说“帮我纠偏下一餐”。")
    return "\n".join(lines)

