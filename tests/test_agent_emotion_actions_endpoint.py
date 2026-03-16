from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import agent as agent_endpoint


def build_payload(**overrides):
    data = {
        "session_id": "sess-1",
        "action_id": "emotion-budget-1",
        "delta_calories": 100,
        "mode": "user_select",
        "reason": "测试",
    }
    data.update(overrides)
    return agent_endpoint.ApplyEmotionBudgetAdjustRequest(**data)


def test_apply_emotion_budget_adjust_success(monkeypatch, run, build_request):
    saved_messages = []

    async def fake_get_session(session_id: str):
        assert session_id == "sess-1"
        return {"id": session_id, "user_id": "u1"}

    async def fake_find_action(session_id: str, action_id: str):
        assert session_id == "sess-1"
        assert action_id == "emotion-budget-1"
        return {"action_id": action_id, "action_type": "emotion_budget_adjust", "can_apply": True}

    async def fake_find_existing(session_id: str, action_id: str):
        return None

    async def fake_adjust(**kwargs):
        assert kwargs["user_id"] == "u1"
        assert kwargs["delta_calories"] == 100
        assert kwargs["mode"] == "user_select"
        return {
            "message": "自动调整完成",
            "applied": 100,
            "capped": False,
            "effective_goal": 2000,
            "goal_source": "explicit",
            "goal_seeded": False,
            "used_provider": "mcp",
        }

    async def fake_save_message(session_id: str, role: str, content: str, trace=None):
        saved_messages.append(
            {
                "session_id": session_id,
                "role": role,
                "content": content,
                "trace": trace,
            }
        )
        return SimpleNamespace()

    monkeypatch.setattr(agent_endpoint.agent_service, "get_session", fake_get_session)
    monkeypatch.setattr(agent_endpoint, "_find_emotion_ui_action", fake_find_action)
    monkeypatch.setattr(
        agent_endpoint,
        "_find_existing_emotion_action_result",
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

    response = run(
        agent_endpoint.apply_emotion_budget_adjust(
            build_payload(),
            build_request(),
        )
    )

    assert response.action_id == "emotion-budget-1"
    assert response.requested == 100
    assert response.applied == 100
    assert response.used_provider == "mcp"
    assert response.effective_goal == 2000
    assert response.goal_source == "explicit"
    assert response.goal_seeded is False
    assert saved_messages
    assert saved_messages[0]["role"] == "assistant"
    assert saved_messages[0]["trace"][0]["action"] == "emotion_budget_adjust_result"
    assert saved_messages[0]["trace"][1]["action"] == "ui_action"
    assert (
        saved_messages[0]["trace"][1]["content"]["action_type"]
        == "smart_recommendation_card"
    )


def test_apply_emotion_budget_adjust_idempotent(monkeypatch, run, build_request):
    async def fake_get_session(session_id: str):
        return {"id": session_id, "user_id": "u1"}

    async def fake_find_action(session_id: str, action_id: str):
        return {"action_id": action_id, "action_type": "emotion_budget_adjust", "can_apply": True}

    async def fake_find_existing(session_id: str, action_id: str):
        return {
            "action_id": action_id,
            "requested": 100,
            "applied": 80,
            "capped": True,
            "effective_goal": 1880,
            "used_provider": "local",
            "mode": "auto_timeout",
            "message": "已完成",
        }

    async def should_not_adjust(**kwargs):
        raise AssertionError("idempotent path should not call adjust_today_budget")

    monkeypatch.setattr(agent_endpoint.agent_service, "get_session", fake_get_session)
    monkeypatch.setattr(agent_endpoint, "_find_emotion_ui_action", fake_find_action)
    monkeypatch.setattr(
        agent_endpoint,
        "_find_existing_emotion_action_result",
        fake_find_existing,
    )
    monkeypatch.setattr(
        agent_endpoint.emotion_budget_service,
        "adjust_today_budget",
        should_not_adjust,
    )

    response = run(
        agent_endpoint.apply_emotion_budget_adjust(
            build_payload(mode="auto_timeout"),
            build_request(),
        )
    )

    assert response.applied == 80
    assert response.capped is True
    assert response.used_provider == "local"


def test_apply_emotion_budget_adjust_cooldown_skips_followup_card(monkeypatch, run, build_request):
    saved_messages = []

    async def fake_get_session(session_id: str):
        return {"id": session_id, "user_id": "u1"}

    async def fake_find_action(session_id: str, action_id: str):
        return {
            "action_id": action_id,
            "action_type": "emotion_budget_adjust",
            "can_apply": True,
            "emotion_level": "medium",
        }

    async def fake_find_existing(session_id: str, action_id: str):
        return None

    async def fake_adjust(**kwargs):
        return {
            "message": "自动调整完成",
            "applied": 100,
            "capped": False,
            "effective_goal": 2000,
            "used_provider": "mcp",
        }

    async def fake_load_state(session_id: str):
        return {
            "last_followup_for_action_id": "emotion-budget-1",
        }

    async def fake_save_state(session_id: str, state: dict):
        return None

    async def fake_save_message(session_id: str, role: str, content: str, trace=None):
        saved_messages.append(
            {
                "session_id": session_id,
                "role": role,
                "content": content,
                "trace": trace,
            }
        )
        return SimpleNamespace()

    monkeypatch.setattr(agent_endpoint.agent_service, "get_session", fake_get_session)
    monkeypatch.setattr(agent_endpoint, "_find_emotion_ui_action", fake_find_action)
    monkeypatch.setattr(
        agent_endpoint,
        "_find_existing_emotion_action_result",
        fake_find_existing,
    )
    monkeypatch.setattr(
        agent_endpoint,
        "_load_emotion_demo_state",
        fake_load_state,
    )
    monkeypatch.setattr(
        agent_endpoint,
        "_save_emotion_demo_state",
        fake_save_state,
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

    response = run(
        agent_endpoint.apply_emotion_budget_adjust(
            build_payload(),
            build_request(),
        )
    )

    assert response.used_provider == "mcp"
    assert saved_messages
    assert len(saved_messages[0]["trace"]) == 1
    assert saved_messages[0]["trace"][0]["action"] == "emotion_budget_adjust_result"


def test_apply_emotion_budget_adjust_unknown_action_id(monkeypatch, run, build_request):
    async def fake_get_session(session_id: str):
        return {"id": session_id, "user_id": "u1"}

    async def fake_find_action(session_id: str, action_id: str):
        return None

    monkeypatch.setattr(agent_endpoint.agent_service, "get_session", fake_get_session)
    monkeypatch.setattr(agent_endpoint, "_find_emotion_ui_action", fake_find_action)

    with pytest.raises(HTTPException) as exc_info:
        run(
            agent_endpoint.apply_emotion_budget_adjust(
                build_payload(),
                build_request(),
            )
        )

    assert exc_info.value.status_code == 404
    assert "action_id" in str(exc_info.value.detail)
