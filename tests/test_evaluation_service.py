from __future__ import annotations

import asyncio
from types import SimpleNamespace


def test_schedule_evaluation_skips_when_disabled(monkeypatch, run):
    import app.services.evaluation_service as eval_mod
    from app.config.evaluation_config import EvaluationConfig

    called = {"create": 0}

    class FakeRepo:
        async def create(self, **_kwargs):
            called["create"] += 1
            return SimpleNamespace(id="e1")

    monkeypatch.setattr(eval_mod, "evaluation_repository", FakeRepo())

    service = eval_mod.EvaluationService(config=EvaluationConfig(enabled=False))

    run(
        service.schedule_evaluation(
            message_id="m1",
            conversation_id="c1",
            query="q",
            context="ctx",
            response="r",
        )
    )
    assert called["create"] == 0


def test_schedule_evaluation_skips_when_no_context(monkeypatch, run):
    import app.services.evaluation_service as eval_mod
    from app.config.evaluation_config import EvaluationConfig

    called = {"create": 0}

    class FakeRepo:
        async def create(self, **_kwargs):
            called["create"] += 1
            return SimpleNamespace(id="e1")

    monkeypatch.setattr(eval_mod, "evaluation_repository", FakeRepo())

    service = eval_mod.EvaluationService(
        config=EvaluationConfig(enabled=True, async_mode=False, sample_rate=1.0)
    )

    run(
        service.schedule_evaluation(
            message_id="m1",
            conversation_id="c1",
            query="q",
            context="",
            response="r",
        )
    )
    assert called["create"] == 0


def test_schedule_evaluation_creates_record_and_runs_when_sync(monkeypatch, run):
    import app.services.evaluation_service as eval_mod
    from app.config.evaluation_config import EvaluationConfig

    created = {"kwargs": None}
    ran = {"args": None}

    class FakeRepo:
        async def create(self, **kwargs):
            created["kwargs"] = kwargs
            return SimpleNamespace(id="e1")

        async def update_results(self, **_kwargs):
            raise AssertionError("update_results should not be called in this test")

    async def fake_run_evaluation(self, evaluation_id, query, context, response, **_kwargs):
        ran["args"] = (evaluation_id, query, context, response)

    monkeypatch.setattr(eval_mod, "evaluation_repository", FakeRepo())
    monkeypatch.setattr(eval_mod.EvaluationService, "_run_evaluation", fake_run_evaluation)

    service = eval_mod.EvaluationService(
        config=EvaluationConfig(enabled=True, async_mode=False, sample_rate=1.0)
    )

    run(
        service.schedule_evaluation(
            message_id="m1",
            conversation_id="c1",
            query="q",
            context="ctx",
            response="r",
            rewritten_query="rq",
            user_id="u1",
        )
    )
    assert created["kwargs"] is not None
    assert created["kwargs"]["message_id"] == "m1"
    assert created["kwargs"]["conversation_id"] == "c1"
    assert created["kwargs"]["query"] == "q"
    assert created["kwargs"]["context"] == "ctx"
    assert created["kwargs"]["response"] == "r"
    assert created["kwargs"]["rewritten_query"] == "rq"
    assert created["kwargs"]["user_id"] == "u1"

    assert ran["args"] == ("e1", "q", "ctx", "r")


def test_run_evaluation_success_updates_results(monkeypatch, run):
    import app.services.evaluation_service as eval_mod
    from app.config.evaluation_config import EvaluationConfig

    updated = {"kwargs": None}

    class FakeRepo:
        async def update_results(self, **kwargs):
            updated["kwargs"] = kwargs

    async def fake_evaluate(_query, _context, _response):
        return {"faithfulness": 0.9}

    monkeypatch.setattr(eval_mod, "evaluation_repository", FakeRepo())

    service = eval_mod.EvaluationService(
        config=EvaluationConfig(enabled=True, async_mode=False, timeout_seconds=5)
    )
    monkeypatch.setattr(service, "evaluate", fake_evaluate)

    run(
        service._run_evaluation(
            evaluation_id="e1",
            query="q",
            context="ctx",
            response="r",
            user_id="u1",
            conversation_id="c1",
        )
    )

    assert updated["kwargs"] is not None
    assert updated["kwargs"]["evaluation_id"] == "e1"
    assert updated["kwargs"]["status"] == "completed"
    assert updated["kwargs"]["results"] == {"faithfulness": 0.9}
    assert isinstance(updated["kwargs"]["duration_ms"], int)
    assert updated["kwargs"]["duration_ms"] >= 0


def test_run_evaluation_timeout_marks_failed(monkeypatch, run):
    import app.services.evaluation_service as eval_mod
    from app.config.evaluation_config import EvaluationConfig

    updated = {"kwargs": None}

    class FakeRepo:
        async def update_results(self, **kwargs):
            updated["kwargs"] = kwargs

    async def slow_evaluate(_query, _context, _response):
        await asyncio.sleep(0.1)
        return {"faithfulness": 0.0}

    monkeypatch.setattr(eval_mod, "evaluation_repository", FakeRepo())

    service = eval_mod.EvaluationService(
        config=EvaluationConfig(enabled=True, async_mode=False, timeout_seconds=0)
    )
    monkeypatch.setattr(service, "evaluate", slow_evaluate)

    run(
        service._run_evaluation(
            evaluation_id="e1",
            query="q",
            context="ctx",
            response="r",
        )
    )

    assert updated["kwargs"] is not None
    assert updated["kwargs"]["status"] == "failed"
    assert updated["kwargs"]["results"] == {}
    assert "timed out" in (updated["kwargs"]["error_message"] or "").lower()


def test_run_evaluation_exception_marks_failed(monkeypatch, run):
    import app.services.evaluation_service as eval_mod
    from app.config.evaluation_config import EvaluationConfig

    updated = {"kwargs": None}

    class FakeRepo:
        async def update_results(self, **kwargs):
            updated["kwargs"] = kwargs

    async def bad_evaluate(_query, _context, _response):
        raise RuntimeError("boom")

    monkeypatch.setattr(eval_mod, "evaluation_repository", FakeRepo())

    service = eval_mod.EvaluationService(
        config=EvaluationConfig(enabled=True, async_mode=False, timeout_seconds=5)
    )
    monkeypatch.setattr(service, "evaluate", bad_evaluate)

    run(
        service._run_evaluation(
            evaluation_id="e1",
            query="q",
            context="ctx",
            response="r",
        )
    )

    assert updated["kwargs"] is not None
    assert updated["kwargs"]["status"] == "failed"
    assert updated["kwargs"]["results"] == {}
    assert "boom" in (updated["kwargs"]["error_message"] or "")

