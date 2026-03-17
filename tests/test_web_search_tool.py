from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest


class _FakeLLM:
    def __init__(self, tool_calls):
        self._tool_calls = tool_calls

    def bind_tools(self, *_args, **_kwargs):
        return self

    def with_config(self, **_kwargs):
        return self

    async def ainvoke(self, _messages):
        return SimpleNamespace(tool_calls=self._tool_calls)


class _FakeProvider:
    def __init__(self, tool_calls):
        self._llm = _FakeLLM(tool_calls)

    def create_llm(self, *_args, **_kwargs):
        return self._llm


def test_web_search_decide_search_disabled_returns_low_confidence(run):
    from app.tools.web_search import WebSearchTool

    tool = WebSearchTool(provider=_FakeProvider(tool_calls=[]))
    tool.enabled = False

    decision = run(
        tool.decide_search(
            query="q",
            document_summary={},
            history_text="",
            user_id="u1",
            conversation_id="c1",
        )
    )
    assert decision.confidence == 0
    assert decision.search_params is None
    assert "disabled" in decision.reason.lower()


def test_web_search_decide_search_no_tool_call_is_safe(run):
    from app.tools.web_search import WebSearchTool

    tool = WebSearchTool(provider=_FakeProvider(tool_calls=[]))
    tool.enabled = True

    decision = run(
        tool.decide_search(
            query="q",
            document_summary={"dish_name": ["a"]},
            history_text="H",
            user_id="u1",
            conversation_id="c1",
        )
    )
    assert decision.confidence == 0
    assert decision.search_params is None
    assert "LLM" in decision.reason or "工具" in decision.reason


def test_web_search_decide_search_parses_tool_call_and_clamps_confidence(run):
    from app.tools.web_search import WebSearchTool

    tool = WebSearchTool(
        provider=_FakeProvider(
            tool_calls=[
                {
                    "args": {
                        "confidence": 99,
                        "search_query": "best mapo tofu",
                        "reason": "needs web",
                    }
                }
            ]
        )
    )
    tool.enabled = True

    decision = run(
        tool.decide_search(
            query="mapo tofu",
            document_summary={},
            history_text="H",
        )
    )
    assert decision.confidence == 10
    assert decision.search_params is not None
    assert decision.search_params.query == "best mapo tofu"
    assert decision.search_params.max_results >= 1
    assert decision.should_search is True


def test_web_search_execute_search_returns_empty_when_client_missing(run):
    from app.tools.web_search import WebSearchParams, WebSearchTool

    tool = WebSearchTool(provider=_FakeProvider(tool_calls=[]), api_key="")
    results = run(tool.execute_search(WebSearchParams(query="x", max_results=2)))
    assert results == []


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://www.example.com/a", "example.com"),
        ("https://example.com/a", "example.com"),
        ("not-a-url", ""),
    ],
)
def test_web_search_extract_domain_is_resilient(url, expected):
    from app.tools.web_search import WebSearchTool

    tool = WebSearchTool(provider=_FakeProvider(tool_calls=[]))
    assert tool._extract_domain(url) == expected  # noqa: SLF001


def test_web_search_format_results_for_context_limits_total_length():
    from app.tools.web_search import WebSearchResult, WebSearchTool

    tool = WebSearchTool(provider=_FakeProvider(tool_calls=[]))
    results = [
        WebSearchResult(
            title="t1",
            snippet="x" * 1000,
            source="example.com",
            url="https://example.com/1",
        ),
        WebSearchResult(
            title="t2",
            snippet="y" * 1000,
            source="example.com",
            url="https://example.com/2",
        ),
    ]

    formatted = tool.format_results_for_context(results, max_length=1200)
    assert "t1" in formatted
    # second entry should be truncated away due to max_length.
    assert "t2" not in formatted
