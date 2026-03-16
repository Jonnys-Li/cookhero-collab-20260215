from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.rag.pipeline.metadata_filter import MetadataFilterExtractor


def test_clean_expression_strips_fences_quotes_and_none():
    assert (
        MetadataFilterExtractor._clean_expression('```sql\ncategory == "川菜"\n```')
        == 'category == "川菜"'
    )
    assert MetadataFilterExtractor._clean_expression('"NONE"') is None
    assert MetadataFilterExtractor._clean_expression("NONE") is None
    assert MetadataFilterExtractor._clean_expression("  ") is None


def test_summarize_metadata_includes_sources_and_values():
    text = MetadataFilterExtractor._summarize_metadata(
        {"Global": {"category": ["川菜", "家常菜"], "difficulty": ["easy"]}}
    )
    assert "来源: Global" in text
    assert "- category" in text
    assert "川菜" in text


def test_build_filter_expression_returns_none_when_catalog_empty():
    extractor = MetadataFilterExtractor(provider=SimpleNamespace(create_invoker=lambda *_a, **_k: None))

    async def _run():
        assert await extractor.build_filter_expression("q", {}) is None

    asyncio.run(_run())


def test_build_filter_expression_success_and_none_paths(monkeypatch):
    class FakeLLM:
        def __init__(self, content: str):
            self._content = content

        async def ainvoke(self, _messages):
            return SimpleNamespace(content=self._content)

    class FakeProvider:
        def __init__(self, llm):
            self._llm = llm
            self.calls = 0

        def create_invoker(self, *_args, **_kwargs):
            self.calls += 1
            return self._llm

    provider = FakeProvider(FakeLLM('{"expr": "category == \\"川菜\\""}'))
    extractor = MetadataFilterExtractor(provider=provider)

    async def _run_ok():
        expr = await extractor.build_filter_expression(
            "q",
            {"Global": {"category": ["川菜"]}},
            user_id="u1",
            conversation_id="c1",
        )
        assert expr == 'category == "川菜"'

    asyncio.run(_run_ok())

    provider_none = FakeProvider(FakeLLM('{"expr": "NONE"}'))
    extractor_none = MetadataFilterExtractor(provider=provider_none)

    async def _run_none():
        expr = await extractor_none.build_filter_expression(
            "q",
            {"Global": {"category": ["川菜"]}},
        )
        assert expr is None

    asyncio.run(_run_none())


def test_build_filter_expression_handles_llm_errors():
    class FakeLLM:
        async def ainvoke(self, _messages):
            raise RuntimeError("boom")

    class FakeProvider:
        def create_invoker(self, *_args, **_kwargs):
            return FakeLLM()

    extractor = MetadataFilterExtractor(provider=FakeProvider())

    async def _run():
        expr = await extractor.build_filter_expression(
            "q",
            {"Global": {"category": ["川菜"]}},
        )
        assert expr is None

    asyncio.run(_run())

