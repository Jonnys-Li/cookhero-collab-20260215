from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.security.dependencies import check_message_security
from app.security.guardrails.guard import GuardResult, SecurityCheckResult
from app.security.prompt_guard import ScanResult, ThreatLevel


def test_check_message_security_blocks_on_prompt_guard(monkeypatch):
    called = {"audit": 0}

    def fake_audit(**_kwargs):
        called["audit"] += 1

    from app.security import dependencies as deps

    monkeypatch.setattr(
        deps.prompt_guard,
        "scan",
        lambda _msg: ScanResult(
            threat_level=ThreatLevel.BLOCKED,
            matched_patterns=["p1"],
            sanitized_input="",
            reason="bad",
        ),
    )
    monkeypatch.setattr(deps.audit_logger, "prompt_injection_blocked", fake_audit)

    request = SimpleNamespace(state=SimpleNamespace(user_id="u1"))

    async def _run():
        with pytest.raises(HTTPException) as exc:
            await check_message_security("x", request)
        assert exc.value.status_code == 400
        assert exc.value.detail == "bad"

    asyncio.run(_run())
    assert called["audit"] == 1


def test_check_message_security_blocks_on_guardrails(monkeypatch):
    called = {"audit": 0}

    def fake_audit(**_kwargs):
        called["audit"] += 1

    from app.security import dependencies as deps

    monkeypatch.setattr(
        deps.prompt_guard,
        "scan",
        lambda _msg: ScanResult(
            threat_level=ThreatLevel.SAFE,
            matched_patterns=[],
            sanitized_input="clean",
            reason="",
        ),
    )

    async def fake_guard(_msg):
        return SecurityCheckResult(
            result=GuardResult.BLOCKED,
            reason="guard bad",
            details={"threat_type": "jailbreak"},
        )

    monkeypatch.setattr(deps.nemo_guard, "check_input", fake_guard)
    monkeypatch.setattr(deps.audit_logger, "prompt_injection_blocked", fake_audit)

    request = SimpleNamespace(state=SimpleNamespace(user_id="u1"))

    async def _run():
        with pytest.raises(HTTPException) as exc:
            await check_message_security("x", request)
        assert exc.value.status_code == 400
        assert exc.value.detail == "guard bad"

    asyncio.run(_run())
    assert called["audit"] == 1


def test_check_message_security_allows_on_guardrails_warning(monkeypatch):
    from app.security import dependencies as deps

    monkeypatch.setattr(
        deps.prompt_guard,
        "scan",
        lambda _msg: ScanResult(
            threat_level=ThreatLevel.SAFE,
            matched_patterns=[],
            sanitized_input="clean",
            reason="",
        ),
    )

    async def fake_guard(_msg):
        return SecurityCheckResult(result=GuardResult.WARNING, reason="warn")

    monkeypatch.setattr(deps.nemo_guard, "check_input", fake_guard)

    request = SimpleNamespace(state=SimpleNamespace(user_id="u1"))

    async def _run():
        out = await check_message_security("x", request)
        assert out == "clean"

    asyncio.run(_run())


def test_check_message_security_does_not_block_on_guardrails_errors(monkeypatch):
    from app.security import dependencies as deps

    monkeypatch.setattr(
        deps.prompt_guard,
        "scan",
        lambda _msg: ScanResult(
            threat_level=ThreatLevel.SAFE,
            matched_patterns=[],
            sanitized_input="clean",
            reason="",
        ),
    )

    async def fake_guard(_msg):
        raise RuntimeError("boom")

    monkeypatch.setattr(deps.nemo_guard, "check_input", fake_guard)

    request = SimpleNamespace(state=SimpleNamespace(user_id="u1"))

    async def _run():
        out = await check_message_security("x", request)
        assert out == "clean"

    asyncio.run(_run())

