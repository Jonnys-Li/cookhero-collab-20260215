import asyncio
import uuid
from datetime import date, datetime, timedelta

import pytest

from app.agent.prompts.default import DEFAULT_AGENT_SYSTEM_PROMPT
from app.agent.registry import AgentHub
from app.agent.subagents import register_builtin_subagents
from app.agent.subagents.builtin.emotion_support import EmotionSupportSubagent
from app.agent.subagents.registry import subagent_registry
from app.agent.types import ToolResult
from app.diet.database.models import UserFoodPreferenceModel
from app.diet.service import DietService


class FakePreference:
    def __init__(self, user_id: str):
        self.id = uuid.uuid4()
        self.user_id = user_id
        self.common_foods = []
        self.avoided_foods = []
        self.diet_tags = []
        self.avg_daily_calories_min = None
        self.avg_daily_calories_max = None
        self.deviation_patterns = []
        self.stats = {}
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def to_dict(self) -> dict:
        stats = self.stats or {}
        goals = stats.get("goals", {}) if isinstance(stats, dict) else {}
        return {
            "id": str(self.id),
            "user_id": self.user_id,
            "common_foods": self.common_foods,
            "avoided_foods": self.avoided_foods,
            "diet_tags": self.diet_tags,
            "avg_daily_calories_min": self.avg_daily_calories_min,
            "avg_daily_calories_max": self.avg_daily_calories_max,
            "deviation_patterns": self.deviation_patterns,
            "stats": stats,
            "calorie_goal": goals.get("calorie_goal"),
            "protein_goal": goals.get("protein_goal"),
            "fat_goal": goals.get("fat_goal"),
            "carbs_goal": goals.get("carbs_goal"),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class FakeDietRepository:
    def __init__(self):
        self.preferences: dict[str, FakePreference] = {}

    async def get_user_preference(self, user_id: str):
        return self.preferences.get(user_id)

    async def upsert_user_preference(self, user_id: str, **kwargs):
        pref = self.preferences.get(user_id)
        if not pref:
            pref = FakePreference(user_id)
            self.preferences[user_id] = pref

        for key, value in kwargs.items():
            if hasattr(pref, key):
                setattr(pref, key, value)
        pref.updated_at = datetime.utcnow()
        return pref


def run(coro):
    return asyncio.run(coro)


def test_subagent_registry_builtin_contains_emotion_support():
    subagent_registry.clear()
    register_builtin_subagents()
    names = set(subagent_registry.get_builtin_names())
    assert "diet_planner" in names
    assert "emotion_support" in names


def test_emotion_subagent_crisis_short_circuit(monkeypatch):
    async def should_not_run_with_tools(*args, **kwargs):
        raise AssertionError("Crisis path should not enter run_with_tools")

    monkeypatch.setattr(
        EmotionSupportSubagent,
        "run_with_tools",
        should_not_run_with_tools,
    )
    subagent = EmotionSupportSubagent(EmotionSupportSubagent.get_default_config())
    result = run(subagent.execute("我想绝食惩罚自己，甚至不想活了"))
    assert result.success is True
    assert result.data["mode"] == "crisis"
    assert "专业医疗" in result.data["result"]


def test_emotion_subagent_whitelist_mcp_filtering(monkeypatch):
    monkeypatch.setattr(
        AgentHub,
        "list_tools",
        classmethod(
            lambda cls, user_id=None: [
                "datetime",
                "diet_analysis",
                "web_search",
                "mcp_city_weather",
                "mcp_fun_music",
                "mcp_diet_auto_adjust_get_today_budget",
                "mcp_internal_sql",
            ]
        ),
    )
    monkeypatch.setattr(
        AgentHub,
        "get_tool",
        classmethod(
            lambda cls, name, user_id=None: object()
            if name
            in {
                "datetime",
                "diet_analysis",
                "web_search",
                "mcp_city_weather",
                "mcp_fun_music",
                "mcp_diet_auto_adjust_get_today_budget",
            }
            else None
        ),
    )

    subagent = EmotionSupportSubagent(EmotionSupportSubagent.get_default_config())
    tools = subagent._build_tool_whitelist("u1")
    assert "mcp_city_weather" in tools
    assert "mcp_fun_music" in tools
    assert "mcp_diet_auto_adjust_get_today_budget" in tools
    assert "mcp_internal_sql" not in tools


def test_adjust_today_budget_cap():
    repo = FakeDietRepository()
    service = DietService(repository=repo)

    run(service.update_user_preference("u1", calorie_goal=2000))
    first = run(service.adjust_today_budget("u1", 120, reason="first"))
    second = run(service.adjust_today_budget("u1", 120, reason="second"))
    budget = run(service.get_today_budget("u1"))

    assert first["applied_delta"] == 120
    assert second["applied_delta"] == 30
    assert second["capped"] is True
    assert budget["today_adjustment"] == 150
    assert budget["remaining_adjustment_cap"] == 0


def test_adjust_today_budget_positive_only():
    repo = FakeDietRepository()
    service = DietService(repository=repo)

    with pytest.raises(ValueError):
        run(service.adjust_today_budget("u1", 0))
    with pytest.raises(ValueError):
        run(service.adjust_today_budget("u1", -20))


def test_get_today_budget_effective_goal():
    repo = FakeDietRepository()
    service = DietService(repository=repo)

    run(service.update_user_preference("u1", calorie_goal=1800))
    run(service.adjust_today_budget("u1", 100, reason="comfort"))
    budget = run(service.get_today_budget("u1"))

    assert budget["base_goal"] == 1800
    assert budget["today_adjustment"] == 100
    assert budget["effective_goal"] == 1900
    assert budget["remaining_adjustment_cap"] == 50


def test_update_preferences_goal_persisted_in_stats():
    repo = FakeDietRepository()
    service = DietService(repository=repo)

    result = run(
        service.update_user_preference(
            "u1",
            calorie_goal=2200,
            protein_goal=130.0,
            fat_goal=70.0,
            carbs_goal=260.0,
        )
    )

    stored = repo.preferences["u1"].stats["goals"]
    assert stored["calorie_goal"] == 2200
    assert stored["protein_goal"] == 130.0
    assert result["calorie_goal"] == 2200
    assert result["protein_goal"] == 130.0


def test_model_to_dict_exposes_goal_compat_fields():
    model = UserFoodPreferenceModel()
    model.id = uuid.uuid4()
    model.user_id = "u1"
    model.common_foods = []
    model.avoided_foods = []
    model.diet_tags = []
    model.avg_daily_calories_min = None
    model.avg_daily_calories_max = None
    model.deviation_patterns = []
    model.stats = {
        "goals": {
            "calorie_goal": 2100,
            "protein_goal": 120.0,
            "fat_goal": 60.0,
            "carbs_goal": 250.0,
        }
    }
    model.created_at = datetime.utcnow()
    model.updated_at = datetime.utcnow()

    data = model.to_dict()
    assert data["calorie_goal"] == 2100
    assert data["protein_goal"] == 120.0
    assert data["fat_goal"] == 60.0
    assert data["carbs_goal"] == 250.0


def test_agent_chat_no_mcp_available_graceful_degrade(monkeypatch):
    captured = {}

    async def fake_run_with_tools(
        self,
        task,
        user_id=None,
        background=None,
        event_handler=None,
        tool_names_override=None,
    ):
        captured["tools"] = list(tool_names_override or [])
        return ToolResult(success=True, data={"result": "ok", "iterations": 1})

    monkeypatch.setattr(
        EmotionSupportSubagent,
        "run_with_tools",
        fake_run_with_tools,
    )
    monkeypatch.setattr(
        AgentHub,
        "list_tools",
        classmethod(lambda cls, user_id=None: ["datetime", "diet_analysis", "web_search", "mcp_xxx_sql"]),
    )
    monkeypatch.setattr(
        AgentHub,
        "get_tool",
        classmethod(
            lambda cls, name, user_id=None: object()
            if name in {"datetime", "diet_analysis", "web_search"}
            else None
        ),
    )

    subagent = EmotionSupportSubagent(EmotionSupportSubagent.get_default_config())
    result = run(subagent.execute("今天吃多了，我有点内疚", user_id="u1"))

    assert result.success is True
    assert captured["tools"] == ["datetime", "diet_analysis", "web_search"]


def test_emotion_subagent_trigger_emits_budget_ui_action(monkeypatch):
    captured = {"tools": []}
    events = []

    async def fake_run_with_tools(
        self,
        task,
        user_id=None,
        background=None,
        event_handler=None,
        tool_names_override=None,
    ):
        captured["tools"] = list(tool_names_override or [])
        return ToolResult(success=True, data={"result": "ok", "iterations": 1})

    async def fake_get_today_budget(*, user_id: str, target_date=None):
        assert user_id == "u1"
        return {
            "message": "ok",
            "used_provider": "mcp",
            "budget": {
                "effective_goal": 1950,
                "remaining_adjustment_cap": 50,
            },
        }

    async def handle_event(step):
        events.append(step)

    monkeypatch.setattr(EmotionSupportSubagent, "run_with_tools", fake_run_with_tools)
    monkeypatch.setattr(
        "app.agent.subagents.builtin.emotion_support.emotion_budget_service.get_today_budget",
        fake_get_today_budget,
    )
    monkeypatch.setattr(
        AgentHub,
        "list_tools",
        classmethod(
            lambda cls, user_id=None: [
                "datetime",
                "diet_analysis",
                "web_search",
                "mcp_diet_auto_adjust_get_today_budget",
                "mcp_diet_auto_adjust_auto_adjust_today_budget",
            ]
        ),
    )
    monkeypatch.setattr(
        AgentHub,
        "get_tool",
        classmethod(lambda cls, name, user_id=None: object()),
    )

    subagent = EmotionSupportSubagent(EmotionSupportSubagent.get_default_config())
    result = run(
        subagent.execute(
            "我今天吃多了，很内疚也很焦虑。",
            user_id="u1",
            event_handler=handle_event,
        )
    )

    assert result.success is True
    assert "diet_analysis" not in captured["tools"]
    ui_events = [event for event in events if event.action == "ui_action"]
    assert ui_events
    content = ui_events[0].content
    assert content["action_type"] == "emotion_budget_adjust"
    assert content["default_delta_calories"] == 100
    assert content["timeout_seconds"] == 10


def test_emotion_subagent_non_trigger_does_not_emit_ui_action(monkeypatch):
    events = []

    async def fake_run_with_tools(
        self,
        task,
        user_id=None,
        background=None,
        event_handler=None,
        tool_names_override=None,
    ):
        return ToolResult(success=True, data={"result": "ok", "iterations": 1})

    async def handle_event(step):
        events.append(step)

    monkeypatch.setattr(EmotionSupportSubagent, "run_with_tools", fake_run_with_tools)
    monkeypatch.setattr(
        AgentHub,
        "list_tools",
        classmethod(lambda cls, user_id=None: ["datetime", "diet_analysis", "web_search"]),
    )
    monkeypatch.setattr(
        AgentHub,
        "get_tool",
        classmethod(lambda cls, name, user_id=None: object()),
    )

    subagent = EmotionSupportSubagent(EmotionSupportSubagent.get_default_config())
    run(
        subagent.execute(
            "今天菜谱怎么安排更省时间？",
            user_id="u1",
            event_handler=handle_event,
        )
    )

    assert all(event.action != "ui_action" for event in events)


def test_manual_trigger_mode_prompt_hint():
    assert "subagent_emotion_support" in DEFAULT_AGENT_SYSTEM_PROMPT


def test_adjustment_history_prunes_to_14_days():
    repo = FakeDietRepository()
    service = DietService(repository=repo)
    user_id = "u1"

    old_day = date.today() - timedelta(days=20)
    pref = FakePreference(user_id)
    pref.stats = {
        "today_budget_adjustments": [
            {
                "date": old_day.isoformat(),
                "delta_calories": 60,
                "reason": "old",
                "source": "emotion_subagent",
                "updated_at": datetime.utcnow().isoformat(),
            }
        ]
    }
    repo.preferences[user_id] = pref

    run(service.adjust_today_budget(user_id, 40, reason="new"))
    refreshed = repo.preferences[user_id].stats["today_budget_adjustments"]
    assert all(item["date"] >= (date.today() - timedelta(days=13)).isoformat() for item in refreshed)
