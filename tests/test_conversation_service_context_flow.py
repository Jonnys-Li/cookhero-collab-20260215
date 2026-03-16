from __future__ import annotations

import asyncio
from types import SimpleNamespace


def test_conversation_service_initialize_context_and_save_user_message(monkeypatch):
    import app.services.conversation_service as conv_mod

    service = conv_mod.conversation_service

    calls: dict[str, list] = {"add_message": []}

    async def fake_get_or_create(conversation_id, user_id=None):
        _ = (conversation_id, user_id)
        return SimpleNamespace(id="c1")

    async def fake_get_history(_conv_id, limit=100):
        _ = limit
        return [
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": "hello",
                "sources": [{"type": "rag", "info": "Mapo tofu"}],
            },
        ]

    async def fake_get_compressed_summary(_conv_id):
        return ("summary", 2)

    async def fake_add_message(**kwargs):
        calls["add_message"].append(kwargs)

    async def fake_get_user_by_id(_user_id):
        return SimpleNamespace(profile="p1", user_instruction="i1")

    monkeypatch.setattr(conv_mod.conversation_repository, "get_or_create", fake_get_or_create)
    monkeypatch.setattr(conv_mod.conversation_repository, "get_history", fake_get_history)
    monkeypatch.setattr(conv_mod.conversation_repository, "get_compressed_summary", fake_get_compressed_summary)
    monkeypatch.setattr(conv_mod.conversation_repository, "add_message", fake_add_message)
    monkeypatch.setattr(conv_mod.user_service, "get_user_by_id", fake_get_user_by_id)

    # Keep test deterministic and avoid exercising ContextManager formatting logic.
    monkeypatch.setattr(service.context_manager, "build_history_text", lambda **_kw: "HISTORY")

    async def _run():
        ctx = await service._initialize_context(
            message="m1",
            conversation_id=None,
            user_id="u1",
            extra_options=None,
            images=None,
        )
        assert ctx.conv_id == "c1"
        assert ctx.user_profile == "p1"
        assert ctx.user_instruction == "i1"
        assert ctx.history_text == "HISTORY"

        # Saving a message without images should not attempt uploads.
        await service._save_user_message(ctx)
        assert calls["add_message"]
        assert calls["add_message"][0]["role"] == "user"
        assert calls["add_message"][0]["content"] == "m1"
        assert ctx.history[-1]["content"] == "m1"
        assert ctx.history_text == "HISTORY"

    asyncio.run(_run())


def test_conversation_service_detect_intent_includes_vision_context(monkeypatch):
    import app.services.conversation_service as conv_mod
    from app.conversation.types import ChatContext, ExtraOptions

    service = conv_mod.conversation_service

    seen = {"history_text": None, "user_id": None, "conversation_id": None}

    async def fake_detect(history_text, user_id=None, conversation_id=None):
        seen["history_text"] = history_text
        seen["user_id"] = user_id
        seen["conversation_id"] = conversation_id
        return SimpleNamespace(need_rag=False, intent=SimpleNamespace(value="x"), reason="r")

    monkeypatch.setattr(service.intent_detector, "detect", fake_detect)

    ctx = ChatContext(
        conv_id="c1",
        message="m",
        user_id="u1",
        options=ExtraOptions(),
        history=[],
        history_dicts=[],
        history_text="H",
        compressed_summary=None,
        compressed_count=0,
        vision_context="V",
    )

    async def _run():
        out = await service._detect_intent(ctx)
        assert out.need_rag is False

    asyncio.run(_run())
    assert seen["history_text"] == "H\n\nV"
    assert seen["user_id"] == "u1"
    assert seen["conversation_id"] == "c1"

