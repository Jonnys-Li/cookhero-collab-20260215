from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.rag.pipeline.metadata_filter import MetadataFilterExtractor


@dataclass
class _FakeResponse:
    content: str


class _FakeInvoker:
    def __init__(self, content: str, *, raise_exc: Exception | None = None):
        self._content = content
        self._raise_exc = raise_exc

    async def ainvoke(self, _messages):
        if self._raise_exc is not None:
            raise self._raise_exc
        return _FakeResponse(content=self._content)


class _FakeProvider:
    def __init__(self, invoker: _FakeInvoker):
        self._invoker = invoker

    def create_invoker(self, _llm_type, temperature: float = 0.0):
        return self._invoker


def test_clean_expression_handles_fences_quotes_and_none():
    extractor = MetadataFilterExtractor(provider=_FakeProvider(_FakeInvoker('{"expr":"NONE"}')))

    assert extractor._clean_expression("NONE") is None
    assert extractor._clean_expression('"category == \\"川菜\\""') == 'category == \\"川菜\\"'

    fenced = "```json\ncategory == \"川菜\"\n```"
    assert extractor._clean_expression(fenced) == 'category == "川菜"'


def test_summarize_metadata_formats_sources():
    extractor = MetadataFilterExtractor(provider=_FakeProvider(_FakeInvoker('{"expr":"NONE"}')))
    summary = extractor._summarize_metadata(
        {
            "recipes": {"category": ["川菜", "家常菜"]},
            "personal": {"difficulty": ["简单"]},
        }
    )
    assert "来源: recipes" in summary
    assert "- category (共2个): 川菜、家常菜" in summary
    assert "来源: personal" in summary


def test_build_filter_expression_returns_none_when_catalog_empty():
    extractor = MetadataFilterExtractor(provider=_FakeProvider(_FakeInvoker('{"expr":"NONE"}')))

    async def _run():
        return await extractor.build_filter_expression("q", metadata_catalog={})

    assert asyncio.run(_run()) is None


def test_build_filter_expression_parses_json_and_cleans_expr():
    invoker = _FakeInvoker('{"expr":"category == \\"川菜\\""}')
    extractor = MetadataFilterExtractor(provider=_FakeProvider(invoker))

    async def _run():
        return await extractor.build_filter_expression(
            "想吃川菜",
            metadata_catalog={"recipes": {"category": ["川菜"]}},
            user_id="u1",
            conversation_id="c1",
        )

    expr = asyncio.run(_run())
    assert expr == 'category == "川菜"'


def test_build_filter_expression_returns_none_on_llm_error():
    invoker = _FakeInvoker("", raise_exc=RuntimeError("boom"))
    extractor = MetadataFilterExtractor(provider=_FakeProvider(invoker))

    async def _run():
        return await extractor.build_filter_expression(
            "q",
            metadata_catalog={"recipes": {"category": ["川菜"]}},
        )

    assert asyncio.run(_run()) is None

