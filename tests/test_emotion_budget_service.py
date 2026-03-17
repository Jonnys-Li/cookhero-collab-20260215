from __future__ import annotations

import json
from types import SimpleNamespace

import pytest


def test_emotion_budget_service_pick_mcp_tool_prefers_exact_match(monkeypatch):
    from app.services.emotion_budget_service import EmotionBudgetService
    from app.agent.registry import AgentHub

    monkeypatch.setattr(
        AgentHub,
        "list_tools",
        classmethod(lambda cls, user_id=None: ["mcp_diet_auto_adjust_get_today_budget", "x"]),
    )

    service = EmotionBudgetService()
    picked = service._pick_mcp_tool(  # noqa: SLF001
        "u1",
        preferred="mcp_diet_auto_adjust_get_today_budget",
        suffix="get_today_budget",
    )
    assert picked == "mcp_diet_auto_adjust_get_today_budget"


def test_emotion_budget_service_pick_mcp_tool_falls_back_to_sorted_candidate(monkeypatch):
    from app.services.emotion_budget_service import EmotionBudgetService
    from app.agent.registry import AgentHub

    monkeypatch.setattr(
        AgentHub,
        "list_tools",
        classmethod(
            lambda cls, user_id=None: [
                "mcp_z_get_today_budget",
                "mcp_a_get_today_budget",
            ]
        ),
    )

    service = EmotionBudgetService()
    picked = service._pick_mcp_tool(  # noqa: SLF001
        "u1",
        preferred="mcp_diet_auto_adjust_get_today_budget",
        suffix="get_today_budget",
    )
    assert picked == "mcp_a_get_today_budget"


def test_emotion_budget_service_normalize_payload_accepts_json_string_and_lists():
    from app.services.emotion_budget_service import EmotionBudgetService

    service = EmotionBudgetService()

    payload = {"budget": {"effective_goal": 1800}}
    assert service._normalize_payload(payload) == payload  # noqa: SLF001

    json_payload = json.dumps(payload)
    assert service._normalize_payload(json_payload) == payload  # noqa: SLF001

    # When result.data is a list, service extracts first dict-like JSON.
    mixed = ["not-json", json.dumps(payload)]
    assert service._normalize_payload(mixed) == payload  # noqa: SLF001


def test_emotion_budget_service_get_today_budget_uses_mcp_when_available(monkeypatch, run):
    from app.services.emotion_budget_service import emotion_budget_service
    from app.agent.registry import AgentHub
    from app.agent.types import ToolResult

    monkeypatch.setattr(
        AgentHub,
        "list_tools",
        classmethod(lambda cls, user_id=None: ["mcp_diet_auto_adjust_get_today_budget", "diet_analysis"]),
    )

    class FakeExecutor:
        async def execute(self, tool_name, _arguments):
            assert tool_name == "mcp_diet_auto_adjust_get_today_budget"
            return ToolResult(
                success=True,
                data=json.dumps(
                    {
                        "message": "ok",
                        "budget": {"effective_goal": 1900, "today_adjustment": 0},
                        "goal_source": "explicit",
                        "goal_seeded": True,
                    }
                ),
            )

    monkeypatch.setattr(
        AgentHub,
        "create_tool_executor",
        classmethod(lambda cls, tool_names=None, user_id=None: FakeExecutor()),
    )

    out = run(emotion_budget_service.get_today_budget(user_id="u1"))
    assert out["used_provider"] == "mcp"
    assert out["used_tool"] == "mcp_diet_auto_adjust_get_today_budget"
    assert out["budget"]["effective_goal"] == 1900
    assert out["goal_source"] == "explicit"
    assert out["goal_seeded"] is True


def test_emotion_budget_service_get_today_budget_falls_back_to_local(monkeypatch, run):
    from app.services.emotion_budget_service import EmotionBudgetService
    from app.agent.registry import AgentHub
    from app.agent.types import ToolResult

    monkeypatch.setattr(
        AgentHub,
        "list_tools",
        classmethod(lambda cls, user_id=None: ["mcp_diet_auto_adjust_get_today_budget", "diet_analysis"]),
    )

    class FakeExecutor:
        async def execute(self, tool_name, _arguments):
            if tool_name == "mcp_diet_auto_adjust_get_today_budget":
                # Valid JSON but missing budget -> triggers provider_errors and fallback.
                return ToolResult(success=True, data={"message": "no budget"})
            assert tool_name == "diet_analysis"
            return ToolResult(
                success=True,
                data={"budget": {"effective_goal": 1800, "today_adjustment": 0}},
            )

    monkeypatch.setattr(
        AgentHub,
        "create_tool_executor",
        classmethod(lambda cls, tool_names=None, user_id=None: FakeExecutor()),
    )

    service = EmotionBudgetService()
    out = run(service.get_today_budget(user_id="u1"))
    assert out["used_provider"] == "local"
    assert out["used_tool"] == "diet_analysis"
    assert out["budget"]["effective_goal"] == 1800
    assert any("payload missing budget" in e for e in out["provider_errors"])


def test_emotion_budget_service_adjust_today_budget_validates_delta(run):
    from app.services.emotion_budget_service import EmotionBudgetService

    service = EmotionBudgetService()
    with pytest.raises(ValueError):
        run(service.adjust_today_budget(user_id="u1", delta_calories=1))


def test_emotion_budget_service_adjust_today_budget_mcp_success(monkeypatch, run):
    from app.services.emotion_budget_service import EmotionBudgetService
    from app.agent.registry import AgentHub
    from app.agent.types import ToolResult

    monkeypatch.setattr(
        AgentHub,
        "list_tools",
        classmethod(lambda cls, user_id=None: ["mcp_diet_auto_adjust_auto_adjust_today_budget", "diet_analysis"]),
    )

    class FakeExecutor:
        async def execute(self, tool_name, arguments):
            assert tool_name == "mcp_diet_auto_adjust_auto_adjust_today_budget"
            assert arguments["emotion_level"] == "medium"
            return ToolResult(
                success=True,
                data={
                    "message": "ok",
                    "applied_delta": 100,
                    "effective_goal": 2000,
                    "capped": False,
                    "budget": {"effective_goal": 2000, "today_adjustment": 100},
                    "goal_source": "avg7d",
                    "goal_seeded": False,
                },
            )

    monkeypatch.setattr(
        AgentHub,
        "create_tool_executor",
        classmethod(lambda cls, tool_names=None, user_id=None: FakeExecutor()),
    )

    service = EmotionBudgetService()
    out = run(
        service.adjust_today_budget(
            user_id="u1",
            delta_calories=100,
            reason="because",
            mode="user_select",
        )
    )
    assert out["used_provider"] == "mcp"
    assert out["requested"] == 100
    assert out["applied"] == 100
    assert out["effective_goal"] == 2000
    assert out["goal_source"] == "avg7d"
    assert out["goal_seeded"] is False

