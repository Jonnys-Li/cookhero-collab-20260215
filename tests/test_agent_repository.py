from __future__ import annotations

import asyncio

import app.agent.database.repository as agent_repo_mod
from app.agent.database.repository import AgentRepository


def test_agent_repository_sessions_and_messages(monkeypatch, sqlite_session_context):
    monkeypatch.setattr(agent_repo_mod, "get_session_context", sqlite_session_context)

    repo = AgentRepository()

    async def _run():
        sess = await repo.get_or_create_session(user_id="u-agent", title="t1")
        sess_id = str(sess.id)
        assert sess.user_id == "u-agent"

        # Invalid ids should return safe defaults.
        assert await repo.get_session("not-a-uuid") is None
        assert await repo.get_message_count("not-a-uuid") == 0
        assert await repo.get_compressed_summary("not-a-uuid") == (None, 0)
        assert await repo.update_compressed_summary("not-a-uuid", "s", 1) is False
        assert await repo.update_session_title("not-a-uuid", "x") is False
        assert await repo.delete_session("not-a-uuid") is False

        assert await repo.get_session_metadata(sess_id) == {}
        assert await repo.merge_session_metadata(sess_id, {"a": 1}) is True
        assert await repo.merge_session_metadata(sess_id, "bad") is False  # type: ignore[arg-type]
        md = await repo.get_session_metadata(sess_id)
        assert md.get("a") == 1

        await repo.save_message(
            sess_id,
            "assistant",
            "",
            tool_calls=[{"id": "tool-1", "type": "function"}],
        )
        await repo.save_message(
            sess_id,
            "tool",
            "{\"ok\": true}",
            tool_call_id="call-1",
            tool_name="vision_analysis",
        )
        await repo.save_message(
            sess_id,
            "assistant",
            "hello",
            trace=[{"action": "finish"}],
            thinking_duration_ms=12,
            answer_duration_ms=34,
        )

        models = await repo.get_messages(sess_id)
        assert len(models) == 3

        recent = await repo.get_recent_messages(sess_id, skip=0, limit=10)
        assert [m["role"] for m in recent] == ["assistant", "tool", "assistant"]
        assert recent[0]["content"] is None
        assert "tool_calls" in recent[0]
        assert recent[1]["tool_call_id"] == "call-1"
        assert recent[1]["name"] == "vision_analysis"

        assert await repo.get_message_count(sess_id) == 3

        summary, count = await repo.get_compressed_summary(sess_id)
        assert summary is None and count == 0
        assert await repo.update_compressed_summary(sess_id, "sum", 2) is True
        summary, count = await repo.get_compressed_summary(sess_id)
        assert summary == "sum" and count == 2

        sessions, total = await repo.list_sessions(user_id="u-agent")
        assert total == 1
        assert sessions[0]["id"] == sess_id

        assert await repo.update_session_title(sess_id, "New title") is True
        sess2 = await repo.get_session(sess_id)
        assert sess2 is not None and sess2.title == "New title"

        assert await repo.delete_session(sess_id) is True
        assert await repo.get_session(sess_id) is None

    asyncio.run(_run())

