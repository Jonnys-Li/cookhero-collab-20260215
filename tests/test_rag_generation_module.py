from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.rag.pipeline.generation import GenerationIntegrationModule


def test_generation_module_rewrite_query_uses_provider_invoker():
    class FakeLLM:
        async def ainvoke(self, _messages):
            return SimpleNamespace(content="rewritten")

    class FakeProvider:
        def __init__(self):
            self.calls = 0

        def create_invoker(self, *_args, **_kwargs):
            self.calls += 1
            return FakeLLM()

    provider = FakeProvider()
    module = GenerationIntegrationModule(provider=provider)

    async def _run():
        out = await module.rewrite_query("original", user_id="u1", conversation_id="c1")
        assert out == "rewritten"

    asyncio.run(_run())
    assert provider.calls == 1

