from app.agent.context import AgentContextBuilder
from app.agent.service import AgentService


def test_planning_trigger_patterns():
    builder = AgentContextBuilder()

    assert builder._should_trigger_planning("鸡肉的热量是多少") is False
    assert builder._should_trigger_planning("我暴食后很自责，下一餐怎么吃") is True
    assert builder._should_trigger_planning("帮我纠偏下一餐") is True


def test_collab_plan_disabled_for_pure_factual_query_even_with_subagents_selected():
    builder = AgentContextBuilder()

    plan = builder._build_collab_plan(
        current_message="鸡肉的热量是多少？",
        available_tool_names=[
            "datetime",
            "diet_analysis",
            "subagent_diet_planner",
            "subagent_emotion_support",
            "subagent_cooking_master",
        ],
        has_images=False,
    )

    assert plan is None


def test_should_emit_smart_recommendation_card_gate():
    service = AgentService()

    assert (
        service._should_emit_smart_recommendation_card(
            {
                "planning_triggered": False,
                "emotion_triggered": False,
                "weekly_progress_triggered": False,
            }
        )
        is False
    )
    assert (
        service._should_emit_smart_recommendation_card(
            {
                "planning_triggered": True,
                "emotion_triggered": False,
                "weekly_progress_triggered": False,
            }
        )
        is True
    )
    assert (
        service._should_emit_smart_recommendation_card(
            {
                "planning_triggered": False,
                "emotion_triggered": True,
                "weekly_progress_triggered": False,
            }
        )
        is True
    )
    assert (
        service._should_emit_smart_recommendation_card(
            {
                "planning_triggered": False,
                "emotion_triggered": False,
                "weekly_progress_triggered": True,
            }
        )
        is True
    )

