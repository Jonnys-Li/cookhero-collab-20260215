from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import agent as agent_endpoint


def build_payload(**overrides):
    data = {
        "session_id": "sess-1",
        "action_id": "smart-1",
        "action_kind": "apply_budget_adjust",
        "mode": "user_select",
        "payload": {"delta_calories": 100},
    }
    data.update(overrides)
    return agent_endpoint.ApplySmartActionRequest(**data)


def test_apply_smart_action_budget_success(monkeypatch, run, build_request):
    saved_messages = []

    async def fake_get_session(session_id: str):
        return {"id": session_id, "user_id": "u1"}

    async def fake_find_action(session_id: str, action_id: str):
        return {"action_id": action_id, "action_type": "smart_recommendation_card"}

    async def fake_find_existing(session_id: str, action_id: str, action_kind: str):
        return None

    async def fake_adjust(**kwargs):
        assert kwargs["delta_calories"] == 100
        return {
            "message": "预算调整完成",
            "applied": 100,
            "capped": False,
            "effective_goal": 2000,
            "used_provider": "mcp",
        }

    async def fake_save_message(session_id: str, role: str, content: str, trace=None):
        saved_messages.append((session_id, role, content, trace))
        return SimpleNamespace()

    monkeypatch.setattr(agent_endpoint.agent_service, "get_session", fake_get_session)
    monkeypatch.setattr(agent_endpoint, "_find_smart_ui_action", fake_find_action)
    monkeypatch.setattr(
        agent_endpoint,
        "_find_existing_smart_action_result",
        fake_find_existing,
    )
    monkeypatch.setattr(
        agent_endpoint.emotion_budget_service,
        "adjust_today_budget",
        fake_adjust,
    )
    monkeypatch.setattr(
        agent_endpoint.agent_service.repository,
        "save_message",
        fake_save_message,
    )

    response = run(agent_endpoint.apply_smart_action(build_payload(), build_request()))

    assert response.action_kind == "apply_budget_adjust"
    assert response.applied is True
    assert response.used_provider == "mcp"
    assert response.result["applied"] == 100
    assert saved_messages and saved_messages[0][1] == "assistant"


def test_apply_smart_action_timeout_mode_no_write(monkeypatch, run, build_request):
    async def fake_get_session(session_id: str):
        return {"id": session_id, "user_id": "u1"}

    async def fake_find_action(session_id: str, action_id: str):
        return {"action_id": action_id, "action_type": "smart_recommendation_card"}

    async def fake_find_existing(session_id: str, action_id: str, action_kind: str):
        return None

    async def should_not_adjust(**kwargs):
        raise AssertionError("timeout_suggest_only should not call adjust")

    async def fake_save_message(session_id: str, role: str, content: str, trace=None):
        return SimpleNamespace()

    monkeypatch.setattr(agent_endpoint.agent_service, "get_session", fake_get_session)
    monkeypatch.setattr(agent_endpoint, "_find_smart_ui_action", fake_find_action)
    monkeypatch.setattr(
        agent_endpoint,
        "_find_existing_smart_action_result",
        fake_find_existing,
    )
    monkeypatch.setattr(
        agent_endpoint.emotion_budget_service,
        "adjust_today_budget",
        should_not_adjust,
    )
    monkeypatch.setattr(
        agent_endpoint.agent_service.repository,
        "save_message",
        fake_save_message,
    )

    payload = build_payload(mode="timeout_suggest_only")
    response = run(agent_endpoint.apply_smart_action(payload, build_request()))

    assert response.applied is False
    assert response.used_provider == "none"


def test_apply_smart_action_next_meal_plan(monkeypatch, run, build_request):
    class FakeMeal:
        def __init__(self, data: dict):
            self._data = data

        def to_dict(self):
            return dict(self._data)

    async def fake_get_session(session_id: str):
        return {"id": session_id, "user_id": "u1"}

    async def fake_find_action(session_id: str, action_id: str):
        return {"action_id": action_id, "action_type": "smart_recommendation_card"}

    async def fake_find_existing(session_id: str, action_id: str, action_kind: str):
        return None

    async def fake_add_meal_to_plan(**kwargs):
        assert kwargs["user_id"] == "u1"
        assert kwargs["meal_type"] == "dinner"
        assert kwargs["plan_date"].isoformat() == "2026-03-06"
        return FakeMeal(
            {
                "id": "meal-1",
                "plan_date": kwargs["plan_date"].isoformat(),
                "meal_type": kwargs["meal_type"],
                "dishes": kwargs["dishes"],
            }
        )

    async def fake_save_message(session_id: str, role: str, content: str, trace=None):
        return SimpleNamespace()

    monkeypatch.setattr(agent_endpoint.agent_service, "get_session", fake_get_session)
    monkeypatch.setattr(agent_endpoint, "_find_smart_ui_action", fake_find_action)
    monkeypatch.setattr(
        agent_endpoint,
        "_find_existing_smart_action_result",
        fake_find_existing,
    )
    monkeypatch.setattr(
        agent_endpoint.diet_service.repository,
        "add_meal_to_plan",
        fake_add_meal_to_plan,
    )
    monkeypatch.setattr(
        agent_endpoint.agent_service.repository,
        "save_message",
        fake_save_message,
    )

    payload = build_payload(
        action_kind="apply_next_meal_plan",
        payload={
            "plan_date": "2026-03-06",
            "meal_type": "dinner",
            "dish_name": "鸡胸肉沙拉配酸奶",
            "calories": 460,
        },
    )
    response = run(agent_endpoint.apply_smart_action(payload, build_request()))

    assert response.action_kind == "apply_next_meal_plan"
    assert response.applied is True
    assert response.result["meal_type"] == "dinner"


def test_apply_smart_action_submit_plan_profile(monkeypatch, run, build_request):
    saved_messages = []

    async def fake_get_session(session_id: str):
        return {"id": session_id, "user_id": "u1"}

    async def fake_find_action(session_id: str, action_id: str):
        return {"action_id": action_id, "action_type": "meal_plan_planmode_card"}

    async def fake_find_existing(session_id: str, action_id: str, action_kind: str):
        return None

    async def fake_persist_profile(*, user_id: str, profile: dict):
        assert user_id == "u1"
        assert profile.get("goal") == "fat_loss"
        return {"id": "pref-1"}

    async def fake_goal_context(*, user_id: str, target_date=None):
        assert user_id == "u1"
        return {
            "date": "2026-03-02",
            "base_goal": 2310,
            "effective_goal": 2310,
            "goal_source": "tdee_estimate",
            "goal_seeded": False,
            "estimate_context": {
                "source": "metabolic_profile",
                "tdee_kcal": 2760,
                "recommended_calorie_goal": 2310,
            },
            "uses_tdee_estimate": True,
            "fallback_used": False,
        }

    def fake_build_preview(profile: dict):
        assert profile.get("weekly_intensity") == "balanced"
        return {
            "week_start_date": "2026-03-02",
            "weekly_intensity": "balanced",
            "weekly_intensity_label": "平衡",
            "weekly_hint": "下周保持稳态推进，兼顾执行感和灵活度。",
            "preview_days": [],
            "planned_meals": [],
            "relax_suggestions": [],
            "training_plan": [],
        }

    async def fake_llm_supplement(profile: dict):
        return "这周只要完成 70% 就很棒。"

    async def fake_save_message(session_id: str, role: str, content: str, trace=None):
        saved_messages.append((session_id, role, content, trace))
        return SimpleNamespace()

    monkeypatch.setattr(agent_endpoint.agent_service, "get_session", fake_get_session)
    monkeypatch.setattr(agent_endpoint, "_find_smart_ui_action", fake_find_action)
    monkeypatch.setattr(
        agent_endpoint,
        "_find_existing_smart_action_result",
        fake_find_existing,
    )
    monkeypatch.setattr(
        agent_endpoint,
        "_persist_planmode_profile",
        fake_persist_profile,
    )
    monkeypatch.setattr(
        agent_endpoint.diet_service,
        "get_goal_context",
        fake_goal_context,
    )
    monkeypatch.setattr(
        agent_endpoint,
        "_build_week_plan_preview",
        fake_build_preview,
    )
    monkeypatch.setattr(
        agent_endpoint,
        "_try_generate_plan_llm_supplement",
        fake_llm_supplement,
    )
    monkeypatch.setattr(
        agent_endpoint.agent_service.repository,
        "save_message",
        fake_save_message,
    )

    payload = build_payload(
        action_kind="submit_plan_profile",
        payload={
            "goal": "fat_loss",
            "weekly_intensity": "balanced",
            "food_types": ["high_protein"],
            "restrictions": [],
            "allergies": [],
            "relax_modes": ["breathing"],
            "training_focus": "low_impact",
            "training_minutes_per_day": 25,
            "training_days_per_week": 3,
            "cook_time_minutes": 30,
        },
    )
    response = run(agent_endpoint.apply_smart_action(payload, build_request()))

    assert response.action_kind == "submit_plan_profile"
    assert response.applied is False
    assert response.used_provider == "template+llm"
    assert response.result["preview_action"]["action_type"] == "meal_plan_preview_card"
    assert response.result["goal_context"]["goal_source"] == "tdee_estimate"
    assert response.result["preview_action"]["goal_context"]["estimate_context"]["tdee_kcal"] == 2760
    assert saved_messages and saved_messages[0][1] == "assistant"


def test_apply_smart_action_apply_week_plan(monkeypatch, run, build_request):
    saved_messages = []

    async def fake_get_session(session_id: str):
        return {"id": session_id, "user_id": "u1"}

    async def fake_find_action(session_id: str, action_id: str):
        return {"action_id": action_id, "action_type": "meal_plan_planmode_card"}

    async def fake_find_existing(session_id: str, action_id: str, action_kind: str):
        return None

    async def fake_upsert_week_plan(*, user_id: str, planned_meals: list[dict]):
        assert user_id == "u1"
        assert len(planned_meals) == 1
        return {
            "created_count": 1,
            "updated_count": 0,
            "total_applied": 1,
            "meals": [{"id": "meal-1"}],
        }

    async def fake_save_message(session_id: str, role: str, content: str, trace=None):
        saved_messages.append((session_id, role, content, trace))
        return SimpleNamespace()

    monkeypatch.setattr(agent_endpoint.agent_service, "get_session", fake_get_session)
    monkeypatch.setattr(agent_endpoint, "_find_smart_ui_action", fake_find_action)
    monkeypatch.setattr(
        agent_endpoint,
        "_find_existing_smart_action_result",
        fake_find_existing,
    )
    monkeypatch.setattr(
        agent_endpoint,
        "_upsert_week_plan_meals",
        fake_upsert_week_plan,
    )
    monkeypatch.setattr(
        agent_endpoint.agent_service.repository,
        "save_message",
        fake_save_message,
    )

    payload = build_payload(
        action_kind="apply_week_plan",
        payload={
            "planned_meals": [
                {
                    "plan_date": "2026-03-06",
                    "meal_type": "dinner",
                    "dishes": [{"name": "鸡胸肉沙拉", "calories": 430}],
                }
            ],
        },
    )
    response = run(agent_endpoint.apply_smart_action(payload, build_request()))

    assert response.action_kind == "apply_week_plan"
    assert response.applied is True
    assert response.result["created_count"] == 1
    assert saved_messages and saved_messages[0][1] == "assistant"


def test_apply_smart_action_create_diet_log_success_and_idempotent(monkeypatch, run, build_request):
    saved_messages = []
    log_meal_calls = []

    async def fake_get_session(session_id: str):
        return {"id": session_id, "user_id": "u1"}

    async def fake_find_action(session_id: str, action_id: str):
        return {"action_id": action_id, "action_type": "meal_log_confirm_card"}

    existing_result = {
        "action_id": "smart-1",
        "action_kind": "create_diet_log",
        "mode": "user_select",
        "applied": True,
        "used_provider": "local",
        "message": "已记录本餐，可在饮食管理中查看",
        "result": {
            "log_date": "2026-03-06",
            "meal_type": "lunch",
            "log": {"id": "log-1"},
        },
    }

    async def fake_find_existing(session_id: str, action_id: str, action_kind: str):
        # Simulate idempotency: second apply returns existing trace result without re-writing DB.
        return existing_result if log_meal_calls else None

    async def fake_log_meal(**kwargs):
        log_meal_calls.append(kwargs)
        assert kwargs["user_id"] == "u1"
        assert kwargs["log_date"].isoformat() == "2026-03-06"
        assert kwargs["meal_type"] == "lunch"
        assert kwargs.get("notes") is None
        assert len(kwargs["items"]) == 1
        item = kwargs["items"][0]
        assert item["food_name"] == "鸡胸肉"
        assert item["weight_g"] == 20.0
        assert item["unit"] is None
        assert item["calories"] == 100
        assert item["protein"] == 10.0
        assert item["fat"] == 1.0
        assert item["carbs"] is not None
        return {
            "id": "log-1",
            "user_id": kwargs["user_id"],
            "log_date": kwargs["log_date"].isoformat(),
            "meal_type": kwargs["meal_type"],
            "items": [],
            "total_calories": 100,
            "total_protein": 10.0,
            "total_fat": 1.0,
            "total_carbs": None,
            "created_at": "2026-03-06T12:00:00",
            "updated_at": "2026-03-06T12:00:00",
        }

    async def fake_save_message(session_id: str, role: str, content: str, trace=None):
        saved_messages.append((session_id, role, content, trace))
        return SimpleNamespace()

    monkeypatch.setattr(agent_endpoint.agent_service, "get_session", fake_get_session)
    monkeypatch.setattr(agent_endpoint, "_find_smart_ui_action", fake_find_action)
    monkeypatch.setattr(
        agent_endpoint,
        "_find_existing_smart_action_result",
        fake_find_existing,
    )
    monkeypatch.setattr(agent_endpoint.diet_service, "log_meal", fake_log_meal)
    monkeypatch.setattr(
        agent_endpoint.agent_service.repository,
        "save_message",
        fake_save_message,
    )

    payload = build_payload(
        action_kind="create_diet_log",
        payload={
            "log_date": "2026-03-06",
            "meal_type": "lunch",
            "items": [
                {
                    "food_name": " 鸡胸肉 ",
                    "weight_g": "20",
                    "calories": "100",
                    "protein": "10",
                    "fat": 1,
                }
            ],
        },
    )

    response1 = run(agent_endpoint.apply_smart_action(payload, build_request()))
    assert response1.action_kind == "create_diet_log"
    assert response1.applied is True
    assert response1.result["meal_type"] == "lunch"
    assert log_meal_calls and len(log_meal_calls) == 1
    assert saved_messages and saved_messages[0][1] == "assistant"
    assert saved_messages[0][3] and saved_messages[0][3][0]["subagent_name"] == "diet_logger"

    response2 = run(agent_endpoint.apply_smart_action(payload, build_request()))
    assert response2.applied is True
    assert len(log_meal_calls) == 1
    assert len(saved_messages) == 1


def test_apply_smart_action_create_diet_log_rejects_missing_nutrition(monkeypatch, run, build_request):
    log_meal_calls = []

    async def fake_get_session(session_id: str):
        return {"id": session_id, "user_id": "u1"}

    async def fake_find_action(session_id: str, action_id: str):
        return {"action_id": action_id, "action_type": "meal_log_confirm_card"}

    async def fake_find_existing(session_id: str, action_id: str, action_kind: str):
        return None

    async def fake_log_meal(**kwargs):
        log_meal_calls.append(kwargs)
        raise AssertionError("log_meal should not be called when nutrition is missing")

    async def fake_save_message(session_id: str, role: str, content: str, trace=None):
        return SimpleNamespace()

    monkeypatch.setattr(agent_endpoint.agent_service, "get_session", fake_get_session)
    monkeypatch.setattr(agent_endpoint, "_find_smart_ui_action", fake_find_action)
    monkeypatch.setattr(
        agent_endpoint,
        "_find_existing_smart_action_result",
        fake_find_existing,
    )
    monkeypatch.setattr(agent_endpoint.diet_service, "log_meal", fake_log_meal)
    monkeypatch.setattr(
        agent_endpoint.agent_service.repository,
        "save_message",
        fake_save_message,
    )

    payload = build_payload(
        action_kind="create_diet_log",
        payload={
            "log_date": "2026-03-06",
            "meal_type": "lunch",
            "items": [
                {
                    "food_name": "鸡肉",
                }
            ],
        },
    )

    with pytest.raises(HTTPException) as exc:
        run(agent_endpoint.apply_smart_action(payload, build_request()))
    assert exc.value.status_code == 400
    assert not log_meal_calls


def test_apply_smart_action_create_diet_log_parses_unit_strings(monkeypatch, run, build_request):
    log_meal_calls = []

    async def fake_get_session(session_id: str):
        return {"id": session_id, "user_id": "u1"}

    async def fake_find_action(session_id: str, action_id: str):
        return {"action_id": action_id, "action_type": "meal_log_confirm_card"}

    async def fake_find_existing(session_id: str, action_id: str, action_kind: str):
        return None

    async def fake_log_meal(**kwargs):
        log_meal_calls.append(kwargs)
        assert kwargs["items"][0]["weight_g"] == 20.0
        assert kwargs["items"][0]["calories"] == 120
        assert kwargs["items"][0]["protein"] == 10.0
        assert kwargs["items"][0]["fat"] == 1.0
        assert kwargs["items"][0]["carbs"] == 2.0
        return {"id": "log-1"}

    async def fake_save_message(session_id: str, role: str, content: str, trace=None):
        return SimpleNamespace()

    monkeypatch.setattr(agent_endpoint.agent_service, "get_session", fake_get_session)
    monkeypatch.setattr(agent_endpoint, "_find_smart_ui_action", fake_find_action)
    monkeypatch.setattr(
        agent_endpoint,
        "_find_existing_smart_action_result",
        fake_find_existing,
    )
    monkeypatch.setattr(agent_endpoint.diet_service, "log_meal", fake_log_meal)
    monkeypatch.setattr(
        agent_endpoint.agent_service.repository,
        "save_message",
        fake_save_message,
    )

    payload = build_payload(
        action_kind="create_diet_log",
        payload={
            "log_date": "2026-03-06",
            "meal_type": "lunch",
            "items": [
                {
                    "food_name": "鸡胸肉",
                    "weight_g": "20g",
                    "calories": "120kcal",
                    "protein": "10g",
                    "fat": "1g",
                    "carbs": "2g",
                }
            ],
        },
    )

    response = run(agent_endpoint.apply_smart_action(payload, build_request()))
    assert response.applied is True
    assert log_meal_calls


def test_apply_smart_action_create_diet_log_fills_macros_from_calories(monkeypatch, run, build_request):
    log_meal_calls = []

    async def fake_get_session(session_id: str):
        return {"id": session_id, "user_id": "u1"}

    async def fake_find_action(session_id: str, action_id: str):
        return {"action_id": action_id, "action_type": "meal_log_confirm_card"}

    async def fake_find_existing(session_id: str, action_id: str, action_kind: str):
        return None

    async def fake_log_meal(**kwargs):
        log_meal_calls.append(kwargs)
        item = kwargs["items"][0]
        assert item["calories"] == 200
        assert item["protein"] is not None and item["protein"] > 0
        assert item["fat"] is not None and item["fat"] > 0
        assert item["carbs"] is not None and item["carbs"] > 0
        return {"id": "log-1"}

    async def fake_save_message(session_id: str, role: str, content: str, trace=None):
        return SimpleNamespace()

    monkeypatch.setattr(agent_endpoint.agent_service, "get_session", fake_get_session)
    monkeypatch.setattr(agent_endpoint, "_find_smart_ui_action", fake_find_action)
    monkeypatch.setattr(
        agent_endpoint,
        "_find_existing_smart_action_result",
        fake_find_existing,
    )
    monkeypatch.setattr(agent_endpoint.diet_service, "log_meal", fake_log_meal)
    monkeypatch.setattr(
        agent_endpoint.agent_service.repository,
        "save_message",
        fake_save_message,
    )

    payload = build_payload(
        action_kind="create_diet_log",
        payload={
            "log_date": "2026-03-06",
            "meal_type": "lunch",
            "items": [
                {
                    "food_name": "可乐",
                    "calories": "200kcal",
                }
            ],
        },
    )

    response = run(agent_endpoint.apply_smart_action(payload, build_request()))
    assert response.applied is True
    assert log_meal_calls
