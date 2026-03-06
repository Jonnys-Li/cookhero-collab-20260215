from app.agent.context import AgentContextBuilder


def test_build_collab_plan_with_selected_agents():
    builder = AgentContextBuilder()
    plan = builder._build_collab_plan(
        current_message="我今天吃多了很内疚，顺便看下本周进度",
        available_tool_names=[
            "datetime",
            "diet_analysis",
            "subagent_diet_planner",
            "subagent_emotion_support",
            "subagent_custom_focus",
        ],
        has_images=True,
    )

    assert plan is not None
    assert plan["enabled"] is True

    stages = {stage["id"]: stage for stage in plan["stages"]}
    assert stages["recognition"]["status"] == "pending"
    assert stages["planning"]["status"] == "pending"
    assert stages["emotion"]["status"] == "pending"
    assert stages["weekly_progress"]["status"] == "pending"

    forced_names = [item["name"] for item in plan["force_tool_calls"]]
    assert forced_names[0] == "subagent_diet_planner"
    assert "subagent_custom_focus" in forced_names
    assert "subagent_emotion_support" in forced_names
    assert forced_names.count("diet_analysis") == 2


def test_build_collab_plan_returns_none_without_trigger():
    builder = AgentContextBuilder()
    plan = builder._build_collab_plan(
        current_message="今天天气不错",
        available_tool_names=["datetime", "diet_analysis"],
        has_images=False,
    )
    assert plan is None
