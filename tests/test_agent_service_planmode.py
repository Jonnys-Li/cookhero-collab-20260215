from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

from app.agent.service import AgentService


@dataclass
class _FakeSession:
    id: str
    title: str | None = None


class _FakeRepo:
    def __init__(self):
        self.saved: list[dict] = []

    async def get_or_create_session(self, session_id: str | None, user_id: str):
        # Always create a deterministic id for tests.
        _ = session_id
        return _FakeSession(id=f"sess-{user_id}", title="t1")

    async def save_message(self, session_id: str, role: str, content: str, **kwargs):
        self.saved.append(
            {
                "session_id": session_id,
                "role": role,
                "content": content,
                "kwargs": dict(kwargs),
            }
        )
        return True


def test_agent_service_planmode_short_circuit_saves_messages():
    repo = _FakeRepo()
    service = AgentService(repository=repo)

    # Ensure background compression doesn't keep tasks pending in the event loop.
    async def _noop_compress(*_args, **_kwargs):
        return None

    service.context_compressor.maybe_compress = _noop_compress  # type: ignore[assignment]

    async def _collect():
        events: list[dict] = []
        async for chunk in service.chat(
            session_id=None,
            user_id="u1",
            message="帮我做一个一周饮食计划",
            streaming=False,
        ):
            assert chunk.startswith("data: ")
            payload = json.loads(chunk[len("data: ") :])
            events.append(payload)

        # Let background create_task run (if any).
        await asyncio.sleep(0)
        return events

    events = asyncio.run(_collect())
    types = [e.get("type") for e in events]

    # PlanMode should emit a session event, a UI action card, a short intro text, then done.
    assert types[:4] == ["session", "ui_action", "text", "done"]

    # Messages should be persisted: user + assistant.
    assert [m["role"] for m in repo.saved] == ["user", "assistant"]
    assert repo.saved[0]["content"] == "帮我做一个一周饮食计划"
    assert "PlanMode" in repo.saved[1]["content"]

