from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest


def test_subagent_service_crud_and_enablement(monkeypatch, run, sqlite_session_context):
    import app.services.subagent_service as sub_mod
    from app.agent.registry import AgentHub
    from app.agent.subagents import register_builtin_subagents

    register_builtin_subagents()

    # Use isolated SQLite for deterministic DB operations.
    monkeypatch.setattr(sub_mod, "get_session_context", sqlite_session_context)

    # Allow any non-subagent tool name.
    monkeypatch.setattr(
        AgentHub,
        "get_tool",
        classmethod(lambda cls, name, user_id=None: object()),
    )

    service = sub_mod.SubagentService()
    user_id = "u-subagent"

    created = run(
        service.create_subagent(
            user_id=user_id,
            name="my_helper",
            display_name="My Helper",
            description="d",
            system_prompt="p",
            tools=["web_search"],
            max_iterations=3,
        )
    )
    assert created.name == "my_helper"
    assert created.enabled is True
    assert created.builtin is False
    assert "web_search" in (created.tools or [])

    configs = run(service.list_configs(user_id))
    assert [c.name for c in configs] == ["my_helper"]

    updated = run(
        service.update_subagent(
            user_id=user_id,
            name="my_helper",
            display_name="Renamed",
            description="d2",
            system_prompt="p2",
            tools=["web_search", "datetime"],
            max_iterations=5,
            category="custom",
        )
    )
    assert updated is not None
    assert updated.display_name == "Renamed"
    assert updated.description == "d2"
    assert updated.system_prompt == "p2"
    assert updated.max_iterations == 5
    assert updated.category == "custom"
    assert "datetime" in (updated.tools or [])

    # Custom enable/disable should persist and reflect in returned configs.
    assert run(service.set_enabled(user_id, "my_helper", False)) is True
    all_configs = run(service.sync_user_subagents(user_id))
    my_cfg = next(c for c in all_configs if c.name == "my_helper")
    assert my_cfg.enabled is False

    assert run(service.delete_subagent(user_id, "my_helper")) is True
    assert run(service.list_configs(user_id)) == []


def test_subagent_service_validates_name_and_tools(monkeypatch, run, sqlite_session_context):
    import app.services.subagent_service as sub_mod
    from app.agent.registry import AgentHub

    monkeypatch.setattr(sub_mod, "get_session_context", sqlite_session_context)

    def fake_get_tool(_cls, name, user_id=None):
        if name == "ok_tool":
            return object()
        return None

    monkeypatch.setattr(AgentHub, "get_tool", classmethod(fake_get_tool))

    service = sub_mod.SubagentService()

    with pytest.raises(ValueError):
        run(
            service.create_subagent(
                user_id="u1",
                name="BadName",
                display_name="x",
                description="d",
                system_prompt="p",
            )
        )

    with pytest.raises(ValueError):
        run(
            service.create_subagent(
                user_id="u1",
                name="good_name",
                display_name="x",
                description="d",
                system_prompt="p",
                tools=["missing_tool"],
            )
        )

    with pytest.raises(ValueError):
        run(
            service.create_subagent(
                user_id="u1",
                name="good_name2",
                display_name="x",
                description="d",
                system_prompt="p",
                tools=["subagent_loop"],
            )
        )

    # Valid tool should pass validation and create successfully.
    created = run(
        service.create_subagent(
            user_id="u1",
            name="good_name3",
            display_name="x",
            description="d",
            system_prompt="p",
            tools=["ok_tool"],
        )
    )
    assert created.name == "good_name3"


def test_subagent_service_prevents_builtin_conflicts(monkeypatch, run, sqlite_session_context):
    import app.services.subagent_service as sub_mod
    from app.agent.registry import AgentHub
    from app.agent.subagents import register_builtin_subagents

    register_builtin_subagents()
    monkeypatch.setattr(sub_mod, "get_session_context", sqlite_session_context)
    monkeypatch.setattr(
        AgentHub,
        "get_tool",
        classmethod(lambda cls, name, user_id=None: object()),
    )

    service = sub_mod.SubagentService()

    with pytest.raises(ValueError):
        run(
            service.create_subagent(
                user_id="u1",
                name="diet_planner",
                display_name="x",
                description="d",
                system_prompt="p",
            )
        )

    with pytest.raises(ValueError):
        run(
            service.update_subagent(
                user_id="u1",
                name="diet_planner",
                display_name="nope",
            )
        )


def test_subagent_service_can_toggle_builtin_enablement(monkeypatch, run, sqlite_session_context):
    import app.services.subagent_service as sub_mod
    from app.agent.subagents import register_builtin_subagents

    register_builtin_subagents()
    monkeypatch.setattr(sub_mod, "get_session_context", sqlite_session_context)

    service = sub_mod.SubagentService()
    user_id = "u-builtin-toggle"

    assert run(service.set_enabled(user_id, "emotion_support", False)) is True
    configs = run(service.sync_user_subagents(user_id))
    emotion = next(c for c in configs if c.name == "emotion_support")
    assert emotion.enabled is False

    assert run(service.set_enabled(user_id, "emotion_support", True)) is True
    configs2 = run(service.sync_user_subagents(user_id))
    emotion2 = next(c for c in configs2 if c.name == "emotion_support")
    assert emotion2.enabled is True

