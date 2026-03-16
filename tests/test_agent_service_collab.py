from __future__ import annotations

from app.agent.service_collab import (
    build_collab_fallback_content,
    build_collab_runtime,
    build_collab_timeline_payload,
    build_result_summary,
    finalize_collab_stages,
    record_collab_tool_output,
    update_collab_stage,
)


def test_build_collab_runtime_returns_none_when_disabled():
    assert build_collab_runtime(None, "s1") is None
    assert build_collab_runtime({"enabled": False}, "s1") is None


def test_build_collab_runtime_normalizes_stages_and_forced_calls():
    runtime = build_collab_runtime(
        {
            "enabled": True,
            "stages": [
                {"id": "recognition", "label": "识别", "status": "pending"},
                {"id": "analysis"},
                {"label": "missing-id"},
                "bad",
            ],
            "force_tool_calls": [
                {"name": "diet_analysis", "stage_id": "analysis", "arguments": {"action": "weekly_summary"}},
                {"name": "diet_analysis", "stage_id": "analysis", "arguments": {"action": "deviation"}},
                {"name": "", "stage_id": "noop"},
            ],
            "emotion_triggered": True,
        },
        "s1",
    )
    assert runtime is not None
    assert runtime["session_id"] == "s1"
    assert len(runtime["stages"]) == 2
    assert runtime["stage_expected"]["analysis"] == 2
    assert isinstance(runtime["forced_call_map"], dict) and runtime["forced_call_map"]
    assert runtime["emotion_triggered"] is True

    timeline = build_collab_timeline_payload(runtime)
    assert timeline["action_type"] == "collab_timeline"
    assert isinstance(timeline["stages"], list)


def test_update_collab_stage_updates_first_match():
    runtime = {
        "stages": [
            {"id": "a", "status": "pending", "summary": "", "reason": ""},
            {"id": "b", "status": "pending", "summary": "", "reason": ""},
        ]
    }
    update_collab_stage(runtime, stage_id="b", status="running", summary="ok")
    assert runtime["stages"][1]["status"] == "running"
    assert runtime["stages"][1]["summary"] == "ok"


def test_record_collab_tool_output_persists_outputs_and_promotes_diet_analysis_payloads():
    runtime = {"stage_outputs": {}, "weekly_summary": None, "weekly_deviation": None}

    record_collab_tool_output(
        runtime,
        stage_id="analysis",
        tool_name="other_tool",
        arguments={"a": 1},
        result={"message": "hi"},
        success=True,
    )
    assert runtime["weekly_summary"] is None

    record_collab_tool_output(
        runtime,
        stage_id="analysis",
        tool_name="diet_analysis",
        arguments={"action": "weekly_summary"},
        result={"summary": {"avg_daily_calories": 2000}},
        success=True,
    )
    assert isinstance(runtime["weekly_summary"], dict)

    record_collab_tool_output(
        runtime,
        stage_id="analysis",
        tool_name="diet_analysis",
        arguments={"action": "deviation"},
        result={"analysis": {"total_deviation": 100, "execution_rate": 90}},
        success=True,
    )
    assert isinstance(runtime["weekly_deviation"], dict)


def test_build_result_summary_prefers_message_then_analysis_fallback():
    assert build_result_summary({"message": "hello world"}) == "hello world"
    summary = build_result_summary({"analysis": {"total_deviation": 120, "execution_rate": 80}})
    assert "偏差" in summary
    assert build_result_summary("") == "执行完成"


def test_finalize_collab_stages_marks_running_completed_and_pending_skipped():
    runtime = {
        "stages": [
            {"id": "a", "status": "running", "summary": ""},
            {"id": "b", "status": "pending", "reason": ""},
            {"id": "c", "status": "completed"},
        ]
    }
    finalize_collab_stages(runtime)
    assert runtime["stages"][0]["status"] == "completed"
    assert runtime["stages"][1]["status"] == "skipped"
    assert runtime["stages"][2]["status"] == "completed"


def test_build_collab_fallback_content_renders_stage_lines():
    content = build_collab_fallback_content(
        {
            "stages": [
                {"id": "a", "label": "A", "status": "completed", "summary": "ok"},
                {"id": "b", "label": "B", "status": "failed", "summary": "bad"},
                {"id": "c", "label": "C", "status": "skipped", "reason": "n/a"},
            ]
        },
        include_smart_card=False,
    )
    assert "A" in content and "B" in content and "C" in content

