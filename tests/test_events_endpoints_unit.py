from types import SimpleNamespace

import pytest
from fastapi import HTTPException


def _build_anon_request():
    return SimpleNamespace(state=SimpleNamespace())


def test_events_create_requires_auth(run):
    from app.api.v1.endpoints.events import CreateEventRequest, create_event

    payload = CreateEventRequest(event_name="plan_created", props={"k": "v"})
    with pytest.raises(HTTPException) as exc:
        run(create_event(payload, _build_anon_request()))
    assert exc.value.status_code == 401


def test_events_recent_requires_auth(run):
    from app.api.v1.endpoints.events import list_recent_events

    with pytest.raises(HTTPException) as exc:
        run(list_recent_events(_build_anon_request(), limit=5))
    assert exc.value.status_code == 401


def test_events_create_and_list_happy_path(
    run,
    build_request,
    sqlite_session_context,
    monkeypatch,
):
    import app.database.product_events_repository as repo_module

    monkeypatch.setattr(repo_module, "get_session_context", sqlite_session_context)

    from app.api.v1.endpoints import events as events_endpoint

    request = build_request(user_id="u_test_1")

    created1 = run(
        events_endpoint.create_event(
            events_endpoint.CreateEventRequest(
                event_name="plan_created",
                path="/diet",
                session_id="s1",
                props={"token": "should_not_persist", "nested": {"password": "x"}},
            ),
            request,
        )
    )
    assert created1["user_id"] == "u_test_1"
    assert created1["event_name"] == "plan_created"
    assert created1["path"] == "/diet"
    assert created1["props"]["token"] == "***MASKED***"
    assert created1["props"]["nested"]["password"] == "***MASKED***"

    created2 = run(
        events_endpoint.create_event(
            events_endpoint.CreateEventRequest(
                event_name="log_created",
                props={"ok": True},
            ),
            request,
        )
    )

    recent = run(events_endpoint.list_recent_events(request, limit=10))
    assert "events" in recent
    assert len(recent["events"]) >= 2
    # Newest first (stable by created_at desc, then id desc).
    assert recent["events"][0]["id"] == created2["id"]
    assert recent["events"][1]["id"] == created1["id"]

