from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.rag.pipeline.generation import GenerationIntegrationModule


@dataclass
class _FakeResponse:
    content: str


class _FakeInvoker:
    def __init__(self, content: str):
        self._content = content
        self.calls: list[list] = []

    async def ainvoke(self, messages):
        # The module passes a list of messages from a prompt template.
        self.calls.append(list(messages))
        return _FakeResponse(content=self._content)


class _FakeProvider:
    def __init__(self, invoker: _FakeInvoker):
        self._invoker = invoker
        self.create_calls: list[tuple] = []

    def create_invoker(self, llm_type, temperature: float = 0.0):
        self.create_calls.append((llm_type, temperature))
        return self._invoker


def test_rewrite_query_uses_provider_and_strips_output():
    invoker = _FakeInvoker("  rewritten query  ")
    provider = _FakeProvider(invoker)
    module = GenerationIntegrationModule(provider=provider, llm_type="fast")

    async def _run():
        return await module.rewrite_query("original", user_id="u1", conversation_id="c1")

    rewritten = asyncio.run(_run())
    assert rewritten == "rewritten query"
    assert provider.create_calls, "Expected provider.create_invoker to be called"
    assert invoker.calls, "Expected invoker.ainvoke to be called"


def test_rewrite_query_caches_invoker_instance():
    invoker = _FakeInvoker("same")
    provider = _FakeProvider(invoker)
    module = GenerationIntegrationModule(provider=provider, llm_type="fast")

    async def _run():
        a = await module.rewrite_query("q1")
        b = await module.rewrite_query("q2")
        return a, b

    a, b = asyncio.run(_run())
    assert a == "same"
    assert b == "same"
    assert len(provider.create_calls) == 1

