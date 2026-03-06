import asyncio
from types import SimpleNamespace

from app.api.v1.endpoints import agent as agent_endpoint


def run(coro):
    return asyncio.run(coro)


def build_request(user_id: str = "u1"):
    return SimpleNamespace(state=SimpleNamespace(user_id=user_id))


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


def test_apply_smart_action_budget_success(monkeypatch):
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


def test_apply_smart_action_timeout_mode_no_write(monkeypatch):
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


def test_apply_smart_action_next_meal_plan(monkeypatch):
    async def fake_get_session(session_id: str):
        return {"id": session_id, "user_id": "u1"}

    async def fake_find_action(session_id: str, action_id: str):
        return {"action_id": action_id, "action_type": "smart_recommendation_card"}

    async def fake_find_existing(session_id: str, action_id: str, action_kind: str):
        return None

    async def fake_add_meal(**kwargs):
        assert kwargs["meal_type"] == "dinner"
        return {
            "id": "meal-1",
            "plan_date": kwargs["plan_date"].isoformat(),
            "meal_type": kwargs["meal_type"],
            "dishes": kwargs["dishes"],
        }

    async def fake_save_message(session_id: str, role: str, content: str, trace=None):
        return SimpleNamespace()

    monkeypatch.setattr(agent_endpoint.agent_service, "get_session", fake_get_session)
    monkeypatch.setattr(agent_endpoint, "_find_smart_ui_action", fake_find_action)
    monkeypatch.setattr(
        agent_endpoint,
        "_find_existing_smart_action_result",
        fake_find_existing,
    )
    monkeypatch.setattr(agent_endpoint.diet_service, "add_meal", fake_add_meal)
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
