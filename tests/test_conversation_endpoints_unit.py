from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import conversation as conversation_endpoints


def _make_http_request(user_id: str | None = "u1"):
    return SimpleNamespace(state=SimpleNamespace(user_id=user_id))


def test_conversation_non_streaming_aggregates_sse_events(run, monkeypatch):
    observed: dict[str, str] = {}

    async def fake_security(message: str, _req):
        observed["secured_in"] = message
        return "SECURED"

    async def fake_chat(**kwargs):
        observed["chat_message"] = kwargs.get("message")
        yield f"data: {json.dumps({'type': 'thinking', 'content': 'x'})}\n\n"
        yield f"data: {json.dumps({'type': 'intent', 'data': {'need_rag': False}})}\n\n"
        yield f"data: {json.dumps({'type': 'text', 'content': 'hello'})}\n\n"
        yield f"data: {json.dumps({'type': 'text', 'content': ' world'})}\n\n"
        yield f"data: {json.dumps({'type': 'sources', 'data': [{'type': 'rag'}]})}\n\n"
        yield f"data: {json.dumps({'type': 'done', 'conversation_id': 'c1'})}\n\n"

    monkeypatch.setattr(conversation_endpoints, "check_message_security", fake_security)
    monkeypatch.setattr(conversation_endpoints.conversation_service, "chat", fake_chat)

    async def _run():
        req = conversation_endpoints.ConversationRequest(message=" hi ", stream=False)
        out = await conversation_endpoints.conversation(req, _make_http_request())
        assert out["conversation_id"] == "c1"
        assert out["response"] == "hello world"
        assert out["sources"] == [{"type": "rag"}]
        assert out["intent"] == {"need_rag": False}
        assert observed["secured_in"] == " hi "
        assert observed["chat_message"] == "SECURED"

    run(_run())


def test_get_conversation_history_404_when_missing(run, monkeypatch):
    async def fake_get_history(_conversation_id: str):
        return None

    monkeypatch.setattr(conversation_endpoints.conversation_service, "get_conversation_history", fake_get_history)

    async def _run():
        with pytest.raises(HTTPException) as exc:
            await conversation_endpoints.get_conversation_history("c1")
        assert exc.value.status_code == 404

    run(_run())


def test_clear_conversation_works_and_404s(run, monkeypatch):
    async def fake_clear(_conversation_id: str):
        return False

    monkeypatch.setattr(conversation_endpoints.conversation_service, "clear_conversation", fake_clear)

    async def _run():
        with pytest.raises(HTTPException) as exc:
            await conversation_endpoints.clear_conversation("c1")
        assert exc.value.status_code == 404

    run(_run())

    async def fake_clear_ok(_conversation_id: str):
        return True

    monkeypatch.setattr(conversation_endpoints.conversation_service, "clear_conversation", fake_clear_ok)

    async def _run2():
        out = await conversation_endpoints.clear_conversation("c1")
        assert out["message"]

    run(_run2())


def test_update_conversation_title_works_and_404s(run, monkeypatch):
    async def fake_update(_conversation_id: str, _title: str):
        return False

    monkeypatch.setattr(conversation_endpoints.conversation_service, "update_conversation_title", fake_update)

    async def _run():
        with pytest.raises(HTTPException) as exc:
            await conversation_endpoints.update_conversation_title("c1", conversation_endpoints.UpdateTitleRequest(title="t"))
        assert exc.value.status_code == 404

    run(_run())

    async def fake_update_ok(_conversation_id: str, title: str):
        assert title == "new title"
        return True

    monkeypatch.setattr(conversation_endpoints.conversation_service, "update_conversation_title", fake_update_ok)

    async def _run2():
        out = await conversation_endpoints.update_conversation_title("c1", conversation_endpoints.UpdateTitleRequest(title="new title"))
        assert out["message"]

    run(_run2())


def test_list_conversations_builds_response_model(run, monkeypatch):
    async def fake_list(user_id: str | None, limit: int, offset: int):
        assert user_id == "u1"
        assert limit == 2
        assert offset == 1
        return (
            [
                {
                    "id": "c1",
                    "title": "t1",
                    "created_at": "2026-03-16T00:00:00Z",
                    "updated_at": "2026-03-16T00:00:00Z",
                    "message_count": 3,
                    "last_message_preview": "hi",
                }
            ],
            1,
        )

    monkeypatch.setattr(conversation_endpoints.conversation_service, "list_conversations", fake_list)

    async def _run():
        out = await conversation_endpoints.list_conversations(_make_http_request(user_id="u1"), limit=2, offset=1)
        assert out.total_count == 1
        assert out.limit == 2
        assert out.offset == 1
        assert out.conversations[0].id == "c1"

    run(_run())

