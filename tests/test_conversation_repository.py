from __future__ import annotations

import asyncio
import importlib

conversation_repo_mod = importlib.import_module("app.database.conversation_repository")
ConversationRepository = getattr(conversation_repo_mod, "ConversationRepository")


def test_conversation_repository_crud(monkeypatch, sqlite_session_context):
    # Patch the module-level hard import so repository methods use our temp DB.
    monkeypatch.setattr(conversation_repo_mod, "get_session_context", sqlite_session_context)

    repo = ConversationRepository()

    async def _run():
        conv = await repo.get_or_create(user_id="user-a")
        conv_id = str(conv.id)

        # Invalid ids should not crash and should return safe values.
        assert await repo.get_history("not-a-uuid") is None
        assert await repo.clear("not-a-uuid") is False
        assert await repo.update_title("not-a-uuid", "t") is False
        assert await repo.get_message_count("not-a-uuid") == 0

        msg = await repo.add_message(
            conv_id,
            "user",
            "hello",
            sources=[{"type": "web", "info": "s1"}],
            intent="general_chat",
            thinking=["t1"],
            thinking_duration_ms=12,
            answer_duration_ms=34,
        )
        assert str(msg.conversation_id) == conv_id
        assert msg.content == "hello"

        history = await repo.get_history(conv_id)
        assert isinstance(history, list)
        assert history and history[0]["content"] == "hello"

        models = await repo.get_messages(conv_id, limit=10)
        assert len(models) == 1
        assert models[0].to_dict()["content"] == "hello"

        # Compressed summary helpers
        summary, count = await repo.get_compressed_summary(conv_id)
        assert summary is None and count == 0

        ok = await repo.update_compressed_summary(conv_id, "sum", 1)
        assert ok is True
        summary, count = await repo.get_compressed_summary(conv_id)
        assert summary == "sum" and count == 1

        # Title update + listing
        assert await repo.update_title(conv_id, "My title") is True
        conversations, total = await repo.list_conversations(user_id="user-a")
        assert total == 1
        assert conversations[0]["title"] == "My title"

        assert await repo.get_message_count(conv_id) == 1

        assert await repo.clear(conv_id) is True
        assert await repo.get_history(conv_id) is None

    asyncio.run(_run())


def test_conversation_repository_get_or_create_with_invalid_id_creates_new(
    monkeypatch,
    sqlite_session_context,
):
    monkeypatch.setattr(conversation_repo_mod, "get_session_context", sqlite_session_context)
    repo = ConversationRepository()

    async def _run():
        conv = await repo.get_or_create(conversation_id="bad-id", user_id="user-b")
        assert conv.user_id == "user-b"

    asyncio.run(_run())
