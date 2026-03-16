from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from types import SimpleNamespace

from app.agent.service import AgentService
from app.agent.types import (
    AgentChunk,
    AgentChunkType,
    AgentContext,
    ToolCallInfo,
    ToolResultInfo,
)


@dataclass
class _FakeSession:
    id: str
    title: str | None = None


class _FakeRepo:
    def __init__(self):
        self.saved: list[dict] = []

    async def get_or_create_session(self, session_id: str | None, user_id: str):
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


def test_agent_service_basic_run_emits_text_and_persists_user_and_assistant(monkeypatch):
    repo = _FakeRepo()
    service = AgentService(repository=repo)

    # Keep background compression deterministic.
    async def _noop_compress(*_args, **_kwargs):
        return None

    service.context_compressor.maybe_compress = _noop_compress  # type: ignore[assignment]

    async def fake_build(session, message: str, user_id: str, **_kwargs):
        return AgentContext(
            system_prompt="SYS",
            user_id=user_id,
            session_id=str(session.id),
            current_message=message,
            images=None,
            collab_plan=None,
        )

    service.context_builder.build = fake_build  # type: ignore[assignment]

    class FakeAgent:
        def run(self, _invoker, _context):
            async def _gen():
                yield AgentChunk(AgentChunkType.CONTENT, "hi")
                yield AgentChunk(AgentChunkType.DONE, {"ok": True})

            return _gen()

    monkeypatch.setattr(service, "_get_agent_or_fallback", lambda _name: FakeAgent())

    # Avoid creating real ChatOpenAI instances.
    import app.llm.provider as llm_provider_mod

    class FakeProvider:
        def __init__(self, _config):
            pass

        def create_invoker(self, **_kwargs):
            return SimpleNamespace()

    monkeypatch.setattr(llm_provider_mod, "LLMProvider", FakeProvider)

    async def _collect():
        events: list[dict] = []
        async for chunk in service.chat(
            session_id=None,
            user_id="u1",
            message="hello",
            streaming=False,
        ):
            assert chunk.startswith("data: ")
            events.append(json.loads(chunk[len("data: ") :]))
        await asyncio.sleep(0)
        return events

    events = asyncio.run(_collect())
    types = [e.get("type") for e in events]

    assert types[0] == "session"
    assert "text" in types
    assert types[-1] == "done"

    # Persisted: user message + final assistant message.
    roles = [m["role"] for m in repo.saved]
    assert roles[0] == "user"
    assert roles[-1] == "assistant"
    assert repo.saved[0]["content"] == "hello"
    assert "hi" in repo.saved[-1]["content"]


def test_agent_service_tool_call_and_result_are_persisted(monkeypatch):
    repo = _FakeRepo()
    service = AgentService(repository=repo)

    async def _noop_compress(*_args, **_kwargs):
        return None

    service.context_compressor.maybe_compress = _noop_compress  # type: ignore[assignment]

    async def fake_build(session, message: str, user_id: str, **_kwargs):
        return AgentContext(
            system_prompt="SYS",
            user_id=user_id,
            session_id=str(session.id),
            current_message=message,
            images=None,
            collab_plan=None,
        )

    service.context_builder.build = fake_build  # type: ignore[assignment]

    class FakeAgent:
        def run(self, _invoker, _context):
            async def _gen():
                yield AgentChunk(
                    AgentChunkType.TOOL_CALL,
                    ToolCallInfo(id="tc1", name="calculator", arguments={"a": 1}),
                )
                yield AgentChunk(
                    AgentChunkType.TOOL_RESULT,
                    ToolResultInfo(
                        tool_call_id="tc1",
                        name="calculator",
                        success=True,
                        result={"value": 2},
                    ),
                )
                yield AgentChunk(AgentChunkType.CONTENT, "done")
                yield AgentChunk(AgentChunkType.DONE, {"ok": True})

            return _gen()

    monkeypatch.setattr(service, "_get_agent_or_fallback", lambda _name: FakeAgent())

    import app.llm.provider as llm_provider_mod

    class FakeProvider:
        def __init__(self, _config):
            pass

        def create_invoker(self, **_kwargs):
            return SimpleNamespace()

    monkeypatch.setattr(llm_provider_mod, "LLMProvider", FakeProvider)

    async def _collect():
        events: list[dict] = []
        async for chunk in service.chat(
            session_id=None,
            user_id="u1",
            message="hello",
            streaming=False,
        ):
            events.append(json.loads(chunk[len("data: ") :]))
        await asyncio.sleep(0)
        return events

    events = asyncio.run(_collect())
    types = [e.get("type") for e in events]
    assert "tool_call" in types
    assert "tool_result" in types

    # Persist order: user, assistant(tool_calls), tool(result), assistant(final).
    roles = [m["role"] for m in repo.saved]
    assert roles[0] == "user"
    assert roles[1] == "assistant"
    assert roles[2] == "tool"
    assert roles[-1] == "assistant"

    assert repo.saved[1]["kwargs"].get("tool_calls")
    assert repo.saved[2]["kwargs"].get("tool_call_id") == "tc1"
    assert repo.saved[2]["kwargs"].get("tool_name") == "calculator"

