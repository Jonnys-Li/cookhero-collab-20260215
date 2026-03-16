from __future__ import annotations

import asyncio
import importlib
import uuid


llm_usage_repo_mod = importlib.import_module("app.database.llm_usage_repository")
LLMUsageRepository = getattr(llm_usage_repo_mod, "LLMUsageRepository")


def test_llm_usage_repository_aggregations(monkeypatch, sqlite_session_context):
    monkeypatch.setattr(llm_usage_repo_mod, "get_session_context", sqlite_session_context)

    repo = LLMUsageRepository()

    async def _run():
        conv_id = str(uuid.uuid4())

        await repo.create_log(
            request_id="r1",
            module_name="m1",
            user_id="u1",
            conversation_id=conv_id,
            model_name="model-a",
            tool_name="t1",
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            duration_ms=100,
        )
        await repo.create_log(
            request_id="r2",
            module_name="m1",
            user_id="u1",
            conversation_id=conv_id,
            model_name="model-a",
            tool_name=None,
            input_tokens=20,
            output_tokens=10,
            total_tokens=30,
            duration_ms=200,
        )
        await repo.create_log(
            request_id="r3",
            module_name="m2",
            user_id="u2",
            conversation_id=None,
            model_name="model-b",
            tool_name="t2",
            input_tokens=1,
            output_tokens=1,
            total_tokens=2,
            duration_ms=50,
        )

        summary = await repo.get_summary(user_id="u1", conversation_id=conv_id)
        assert summary["total_calls"] == 2
        assert summary["total_tokens"] == 45
        assert summary["avg_tokens_per_call"] == 22.5

        series = await repo.get_time_series(days=7, granularity="day", user_id="u1")
        assert sum(int(p["call_count"]) for p in series) == 2

        by_module = await repo.get_distribution_by_module(user_id="u1")
        assert any(row["module_name"] == "m1" and row["call_count"] == 2 for row in by_module)

        by_model = await repo.get_distribution_by_model(user_id="u1")
        assert any(row["model_name"] == "model-a" and row["call_count"] == 2 for row in by_model)

        logs = await repo.get_by_conversation(conv_id, limit=10)
        assert len(logs) == 2
        assert {row["request_id"] for row in logs} == {"r1", "r2"}

        distinct_modules = await repo.get_distinct_modules()
        assert "m1" in distinct_modules and "m2" in distinct_modules

        distinct_models = await repo.get_distinct_models()
        assert "model-a" in distinct_models and "model-b" in distinct_models

        distinct_tools = await repo.get_distinct_tools()
        assert "t1" in distinct_tools and "t2" in distinct_tools

        by_tool = await repo.get_distribution_by_tool(user_id="u1")
        assert any(row["tool_name"] == "t1" for row in by_tool)
        assert any(row["tool_name"] == "no_tool" for row in by_tool)

        tool_series = await repo.get_tool_time_series(days=7, granularity="day", user_id="u1")
        assert tool_series

    asyncio.run(_run())

