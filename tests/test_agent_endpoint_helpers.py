from __future__ import annotations

import datetime as dt

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import agent as agent_endpoints


def test_parse_trace_step_accepts_dict_and_json_string():
    assert agent_endpoints._parse_trace_step({"a": 1}) == {"a": 1}
    assert agent_endpoints._parse_trace_step('{"a": 1}') == {"a": 1}
    assert agent_endpoints._parse_trace_step("[1,2]") is None
    assert agent_endpoints._parse_trace_step("not json") is None
    assert agent_endpoints._parse_trace_step(123) is None


def test_extract_trace_content_accepts_dict_and_json_string():
    assert agent_endpoints._extract_trace_content({"x": "y"}) == {"x": "y"}
    assert agent_endpoints._extract_trace_content('{"x": "y"}') == {"x": "y"}
    assert agent_endpoints._extract_trace_content('["x"]') is None
    assert agent_endpoints._extract_trace_content("not json") is None
    assert agent_endpoints._extract_trace_content(None) is None


def test_parse_iso_date_handles_empty_and_valid_and_invalid():
    assert agent_endpoints._parse_iso_date(None) is None
    assert agent_endpoints._parse_iso_date("") is None
    assert agent_endpoints._parse_iso_date("  ") is None
    assert agent_endpoints._parse_iso_date("2026-03-16") == dt.date(2026, 3, 16)

    with pytest.raises(HTTPException) as exc:
        agent_endpoints._parse_iso_date("2026/03/16")
    assert exc.value.status_code == 400


def test_infer_default_next_meal_branches(monkeypatch):
    class FakeDatetime:
        @classmethod
        def now(cls):  # noqa: D401 - signature matches datetime.now()
            return dt.datetime(2026, 3, 16, 9, 0, 0)

    monkeypatch.setattr(agent_endpoints, "datetime", FakeDatetime)
    plan_date, meal_type = agent_endpoints._infer_default_next_meal()
    assert plan_date == dt.date(2026, 3, 16)
    assert meal_type == "lunch"

    class FakeDatetime2:
        @classmethod
        def now(cls):
            return dt.datetime(2026, 3, 16, 12, 0, 0)

    monkeypatch.setattr(agent_endpoints, "datetime", FakeDatetime2)
    _plan_date, _meal_type = agent_endpoints._infer_default_next_meal()
    assert _meal_type == "dinner"

    class FakeDatetime3:
        @classmethod
        def now(cls):
            return dt.datetime(2026, 3, 16, 18, 0, 0)

    monkeypatch.setattr(agent_endpoints, "datetime", FakeDatetime3)
    _plan_date, _meal_type = agent_endpoints._infer_default_next_meal()
    assert _meal_type == "snack"

    class FakeDatetime4:
        @classmethod
        def now(cls):
            return dt.datetime(2026, 3, 16, 22, 0, 0)

    monkeypatch.setattr(agent_endpoints, "datetime", FakeDatetime4)
    plan_date, meal_type = agent_endpoints._infer_default_next_meal()
    assert meal_type == "breakfast"
    assert plan_date == dt.date(2026, 3, 17)


def test_normalize_text_and_lists_and_split_helpers():
    assert agent_endpoints._normalize_text(None) == ""
    assert agent_endpoints._normalize_text("  hi  ") == "hi"
    assert agent_endpoints._normalize_text("x" * 10, max_length=5) == "x" * 5

    assert agent_endpoints._normalize_text_list("not a list") == []
    assert agent_endpoints._normalize_text_list([" a ", "a", "", None, "b"], max_items=10) == [
        "a",
        "b",
    ]
    assert agent_endpoints._normalize_text_list(["x" * 50], item_max_length=10) == ["x" * 10]

    assert agent_endpoints._split_custom_text("") == []
    assert agent_endpoints._split_custom_text("  a, b，c、d; a\nb ") == ["a", "b", "c", "d"]


def test_clamp_int_and_week_start():
    assert agent_endpoints._clamp_int("10", default=1, minimum=0, maximum=9) == 9
    assert agent_endpoints._clamp_int("-1", default=1, minimum=0, maximum=9) == 0
    assert agent_endpoints._clamp_int(None, default=3, minimum=0, maximum=9) == 3

    assert agent_endpoints._get_week_start(dt.date(2026, 3, 18)) == dt.date(2026, 3, 16)


def test_build_plan_profile_applies_defaults_and_normalizes():
    profile = agent_endpoints._build_plan_profile(
        {
            "goal": "INVALID",
            "weekly_intensity": "AGGRESSIVE",
            "training_focus": "CARDIO",
            "food_types": [" high protein ", "high protein", "low carb"],
            "food_type_custom": "fish, eggs",
            "restrictions": ["nuts"],
            "restriction_custom": "nuts, dairy",
            "allergies": "not a list",
            "relax_modes": ["breathing", "unknown"],
            "relax_custom": "walk, journaling",
            "training_minutes_per_day": "999",
            "training_days_per_week": 0,
            "cook_time_minutes": "abc",
            "special_days": "  weekends ",
            "training_custom": "  keep it light ",
        }
    )

    assert profile["goal"] == "fat_loss"
    assert profile["weekly_intensity"] == "aggressive"
    assert profile["training_focus"] == "cardio"
    assert profile["training_minutes_per_day"] == 120
    assert profile["training_days_per_week"] == 1
    assert profile["cook_time_minutes"] == 30
    assert profile["special_days"] == "weekends"
    assert profile["training_custom"] == "keep it light"
    assert "fish" in profile["food_types"]
    assert "dairy" in profile["restrictions"]
    assert profile["allergies"] == []


def test_build_relax_suggestions_has_fallback():
    suggestions = agent_endpoints._build_relax_suggestions(["breathing", "breathing", "walk"])
    assert len(suggestions) == 2
    assert suggestions[0]
    assert suggestions[1]

    fallback = agent_endpoints._build_relax_suggestions([])
    assert len(fallback) == 2


def test_adjust_calories_applies_intensity_delta_and_floor():
    assert agent_endpoints._adjust_calories(500, "conservative") == 580
    assert agent_endpoints._adjust_calories(500, "balanced") == 500
    assert agent_endpoints._adjust_calories(130, "aggressive") == 120


def test_build_meal_candidates_is_deterministic_and_includes_macros():
    candidates = agent_endpoints._build_meal_candidates(
        goal="fat_loss",
        meal_type="breakfast",
        day_index=0,
        weekly_intensity="balanced",
        limit=2,
    )
    assert len(candidates) == 2
    assert candidates[0]["dish_name"]
    assert candidates[0]["calories"]
    assert candidates[0]["protein"] is not None
    assert candidates[0]["nutrition_source"] == "AUTO"


def test_build_weekly_progress_summary_prefers_execution_rate_and_deviation():
    summary = agent_endpoints._build_weekly_progress_summary(
        weekly_summary={"avg_daily_calories": 1888},
        deviation={"analysis": {"execution_rate": 87.4, "total_deviation": -123}},
        intensity_level="balanced",
    )
    assert "87.4%" in summary
    assert "-123" in summary

    summary2 = agent_endpoints._build_weekly_progress_summary(
        weekly_summary={"avg_daily_calories": 1888},
        deviation={},
        intensity_level="conservative",
    )
    assert "1888" in summary2

    summary3 = agent_endpoints._build_weekly_progress_summary(
        weekly_summary={},
        deviation={},
        intensity_level="unknown",
    )
    assert "平衡" in summary3


def test_parse_iso_datetime_accepts_z_suffix():
    parsed = agent_endpoints._parse_iso_datetime("2026-03-16T00:00:00Z")
    assert parsed is not None
    assert parsed.tzinfo is not None

    assert agent_endpoints._parse_iso_datetime("not a date") is None
    assert agent_endpoints._parse_iso_datetime("") is None
    assert agent_endpoints._parse_iso_datetime(123) is None


def test_should_emit_emotion_followup_respects_cooldown_and_dedup(monkeypatch):
    fixed_now = dt.datetime(2026, 3, 16, 0, 0, 0, tzinfo=dt.timezone.utc)

    class FakeDatetime:
        @classmethod
        def fromisoformat(cls, raw: str):
            return dt.datetime.fromisoformat(raw)

        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return fixed_now.replace(tzinfo=None)
            return fixed_now.astimezone(tz)

        @classmethod
        def utcnow(cls):
            return fixed_now.replace(tzinfo=None)

    monkeypatch.setattr(agent_endpoints, "datetime", FakeDatetime)

    assert (
        agent_endpoints._should_emit_emotion_followup(
            "a1", {"last_followup_for_action_id": "a1"}
        )
        is False
    )

    assert agent_endpoints._should_emit_emotion_followup("a1", {}) is True

    # Within cooldown: should not emit
    state = {
        "last_followup_for_action_id": "other",
        "last_followup_at": "2026-03-15T23:59:00Z",
    }
    assert agent_endpoints._should_emit_emotion_followup("a1", state) is False

    # Beyond cooldown: should emit
    state2 = {
        "last_followup_for_action_id": "other",
        "last_followup_at": "2026-03-15T00:00:00Z",
    }
    assert agent_endpoints._should_emit_emotion_followup("a1", state2) is True


def test_build_emotion_followup_smart_action_uses_inferred_next_meal(monkeypatch):
    monkeypatch.setattr(
        agent_endpoints,
        "_infer_default_next_meal",
        lambda: (dt.date(2026, 3, 16), "dinner"),
    )

    class FakeUUID:
        hex = "deadbeef" * 4

    monkeypatch.setattr(agent_endpoints.uuid, "uuid4", lambda: FakeUUID)

    action = agent_endpoints._build_emotion_followup_smart_action(
        session_id="s1",
        parent_action_id="p1",
        emotion_level="high",
        used_provider="mcp",
        effective_goal=1800,
        applied_delta=100,
        capped=True,
    )
    assert action["session_id"] == "s1"
    assert action["parent_action_id"] == "p1"
    assert action["next_meal_options"][0]["meal_type"] == "dinner"
    assert action["next_meal_options"][0]["plan_date"] == "2026-03-16"
