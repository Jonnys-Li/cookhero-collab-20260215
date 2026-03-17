from __future__ import annotations

import asyncio


def test_guardrails_ensure_initialized_importerror_fallback(run):
    from app.security.guardrails.guard import CookHeroGuard

    guard = CookHeroGuard(enabled=True)

    assert run(guard._ensure_initialized()) is False
    assert guard._initialized is True
    assert guard._rails is None


def test_guardrails_calls_rails_and_handles_rejection(run, monkeypatch):
    from app.security.guardrails.guard import CookHeroGuard, GuardResult

    class DummyRails:
        def __init__(self, content: str):
            self._content = content

        async def generate_async(self, *args, **kwargs):  # noqa: ANN001
            return {"content": self._content}

    async def _noop(_duration_ms: int) -> None:
        return None

    guard = CookHeroGuard(enabled=True)
    guard._initialized = True
    guard._rails = DummyRails("抱歉，我无法回答这个问题。")
    # Avoid DB work in background tasks.
    monkeypatch.setattr(guard, "_log_guardrails_usage", _noop)

    async def _run():
        res = await guard.check_input("hello")
        assert res.result == GuardResult.BLOCKED
        assert res.reason

        out = await guard.check_output("hello")
        assert out.result == GuardResult.BLOCKED
        assert out.reason

        # Let background tasks drain (log usage) so asyncio.run doesn't cancel pending tasks.
        await asyncio.sleep(0)

    run(_run())


def test_guardrails_handles_rails_exceptions(run, monkeypatch):
    from app.security.guardrails.guard import CookHeroGuard, GuardResult

    class BoomRails:
        async def generate_async(self, *args, **kwargs):  # noqa: ANN001
            raise RuntimeError("unsafe: blocked by policy")

    async def _noop(_duration_ms: int) -> None:
        return None

    guard = CookHeroGuard(enabled=True)
    guard._initialized = True
    guard._rails = BoomRails()
    monkeypatch.setattr(guard, "_log_guardrails_usage", _noop)

    async def _run():
        res = await guard.check_input("hello")
        assert res.result == GuardResult.BLOCKED
        assert "blocked" in res.reason.lower()
        await asyncio.sleep(0)

    run(_run())

