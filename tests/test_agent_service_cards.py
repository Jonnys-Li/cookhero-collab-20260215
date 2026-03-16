from __future__ import annotations

from datetime import datetime

from app.agent.service_cards import (
    build_meal_log_confirm_action,
    build_meal_plan_planmode_action,
    build_smart_recommendation_action,
    infer_next_meal_plan,
    infer_planmode_default_intensity,
    should_emit_smart_recommendation_card,
)


def test_build_meal_log_confirm_action_shape():
    action = build_meal_log_confirm_action(
        session_id="s1",
        suggested_log_date="2026-03-16",
        suggested_meal_type="lunch",
        items=[{"food_name": "鸡胸肉", "weight_g": 200}],
    )
    assert action["action_type"] == "meal_log_confirm_card"
    assert action["session_id"] == "s1"
    assert action["suggested_meal_type"] == "lunch"
    assert isinstance(action["items"], list)


def test_infer_planmode_default_intensity_by_deviation():
    assert infer_planmode_default_intensity(None) == "balanced"
    assert infer_planmode_default_intensity({"weekly_deviation": {"total_deviation": 1500}}) == "conservative"
    assert infer_planmode_default_intensity({"weekly_deviation": {"total_deviation": 200}}) == "aggressive"
    assert infer_planmode_default_intensity({"weekly_deviation": {"total_deviation": 600}}) == "balanced"


def test_build_meal_plan_planmode_action_contains_defaults_and_session():
    action = build_meal_plan_planmode_action(runtime=None, session_id="s1")
    assert action["action_type"] == "meal_plan_planmode_card"
    assert action["session_id"] == "s1"
    assert action["defaults"]["weekly_intensity"] in {"conservative", "balanced", "aggressive"}


def test_infer_next_meal_plan_is_deterministic_with_now():
    day, meal = infer_next_meal_plan(now=datetime(2024, 1, 1, 9, 0, 0))
    assert str(day) == "2024-01-01"
    assert meal == "lunch"

    day, meal = infer_next_meal_plan(now=datetime(2024, 1, 1, 22, 0, 0))
    assert str(day) == "2024-01-02"
    assert meal == "breakfast"


def test_should_emit_smart_recommendation_card_gate():
    assert (
        should_emit_smart_recommendation_card(
            {
                "planning_triggered": False,
                "emotion_triggered": False,
                "weekly_progress_triggered": False,
            }
        )
        is False
    )
    assert should_emit_smart_recommendation_card({"planning_triggered": True}) is True
    assert should_emit_smart_recommendation_card({"emotion_triggered": True}) is True
    assert should_emit_smart_recommendation_card({"weekly_progress_triggered": True}) is True


def test_build_smart_recommendation_action_has_expected_sections():
    action = build_smart_recommendation_action(
        {
            "session_id": "s1",
            "planning_triggered": True,
            "weekly_deviation": {"execution_rate": 80, "total_deviation": -200},
        }
    )
    assert action["action_type"] == "smart_recommendation_card"
    assert action["session_id"] == "s1"
    assert isinstance(action.get("next_meal_options"), list)
    assert isinstance(action.get("relax_suggestions"), list)
    assert isinstance(action.get("weekly_progress"), dict)

