from __future__ import annotations

import datetime as dt

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import llm_stats as llm_stats_endpoints


class _FakeLLMUsageRepo:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    async def get_summary(self, **kwargs):
        self.calls.append(("get_summary", kwargs))
        return {"summary": True}

    async def get_time_series(self, **kwargs):
        self.calls.append(("get_time_series", kwargs))
        return [{"t": "x"}]

    async def get_distribution_by_module(self, **kwargs):
        self.calls.append(("get_distribution_by_module", kwargs))
        return [{"module": "agent"}]

    async def get_distribution_by_model(self, **kwargs):
        self.calls.append(("get_distribution_by_model", kwargs))
        return [{"model": "gpt"}]

    async def get_by_conversation(self, **kwargs):
        self.calls.append(("get_by_conversation", kwargs))
        return [
            {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30},
            {"input_tokens": None, "output_tokens": 1, "total_tokens": 1},
        ]

    async def get_distinct_modules(self):
        return ["agent", "conversation"]

    async def get_distinct_models(self):
        return ["gpt-x"]

    async def get_distinct_tools(self):
        return ["tool_a"]

    async def get_distribution_by_tool(self, **kwargs):
        self.calls.append(("get_distribution_by_tool", kwargs))
        return [{"tool": "tool_a"}]

    async def get_tool_time_series(self, **kwargs):
        self.calls.append(("get_tool_time_series", kwargs))
        return [{"t": "x"}]


def test_get_llm_stats_summary_parses_dates_and_passes_user_id(run, build_request, monkeypatch):
    fake = _FakeLLMUsageRepo()
    monkeypatch.setattr(llm_stats_endpoints, "llm_usage_repository", fake)

    async def _run():
        req = build_request(user_id="u1")
        out = await llm_stats_endpoints.get_llm_stats_summary(
            req,
            start_date="2026-03-01T00:00:00",
            end_date="2026-03-02T00:00:00",
            conversation_id="c1",
        )
        assert out == {"summary": True}
        name, kwargs = fake.calls[0]
        assert name == "get_summary"
        assert kwargs["user_id"] == "u1"
        assert isinstance(kwargs["start_date"], dt.datetime)
        assert isinstance(kwargs["end_date"], dt.datetime)
        assert kwargs["conversation_id"] == "c1"

    run(_run())


def test_get_llm_stats_summary_rejects_invalid_date(run, build_request, monkeypatch):
    fake = _FakeLLMUsageRepo()
    monkeypatch.setattr(llm_stats_endpoints, "llm_usage_repository", fake)

    async def _run():
        req = build_request(user_id="u1")
        with pytest.raises(HTTPException) as exc:
            await llm_stats_endpoints.get_llm_stats_summary(
                req,
                start_date="not-a-date",
                end_date=None,
                conversation_id=None,
            )
        assert exc.value.status_code == 400

    run(_run())


def test_time_series_and_tool_time_series_shape(run, build_request, monkeypatch):
    fake = _FakeLLMUsageRepo()
    monkeypatch.setattr(llm_stats_endpoints, "llm_usage_repository", fake)

    async def _run():
        req = build_request(user_id="u1")
        out = await llm_stats_endpoints.get_llm_stats_time_series(
            req,
            days=7,
            granularity="day",
            module_name="agent",
            model_name="gpt-x",
        )
        assert out["data_points"] == 1

        out2 = await llm_stats_endpoints.get_tool_time_series(
            req,
            days=7,
            granularity="hour",
            model_name=None,
            module_name=None,
        )
        assert out2["data_points"] == 1

    run(_run())


def test_distributions_parse_dates(run, build_request, monkeypatch):
    fake = _FakeLLMUsageRepo()
    monkeypatch.setattr(llm_stats_endpoints, "llm_usage_repository", fake)

    async def _run():
        req = build_request(user_id="u1")
        out = await llm_stats_endpoints.get_distribution_by_module(
            req,
            start_date="2026-03-01T00:00:00",
            end_date="2026-03-02T00:00:00",
        )
        assert out["count"] == 1

        out2 = await llm_stats_endpoints.get_distribution_by_model(
            req,
            start_date=None,
            end_date=None,
        )
        assert out2["count"] == 1

        out3 = await llm_stats_endpoints.get_distribution_by_tool(
            req,
            start_date=None,
            end_date=None,
            model_name="gpt-x",
            module_name="agent",
        )
        assert out3["count"] == 1

    run(_run())


def test_conversation_stats_aggregates_totals(run, build_request, monkeypatch):
    fake = _FakeLLMUsageRepo()
    monkeypatch.setattr(llm_stats_endpoints, "llm_usage_repository", fake)

    async def _run():
        req = build_request(user_id="u1")
        out = await llm_stats_endpoints.get_conversation_llm_stats(req, conversation_id="c1", limit=10)
        assert out["count"] == 2
        assert out["total_input_tokens"] == 10
        assert out["total_output_tokens"] == 21
        assert out["total_tokens"] == 31

    run(_run())


def test_available_facets(run, monkeypatch):
    fake = _FakeLLMUsageRepo()
    monkeypatch.setattr(llm_stats_endpoints, "llm_usage_repository", fake)

    async def _run():
        modules = await llm_stats_endpoints.get_available_modules()
        assert modules == {"modules": ["agent", "conversation"], "count": 2}

        models = await llm_stats_endpoints.get_available_models()
        assert models == {"models": ["gpt-x"], "count": 1}

        tools = await llm_stats_endpoints.get_available_tools()
        assert tools == {"tools": ["tool_a"], "count": 1}

    run(_run())

