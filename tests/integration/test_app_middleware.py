from __future__ import annotations

import os
from contextlib import contextmanager

import pytest
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.main import app


@contextmanager
def _set_env(name: str, value: str):
    old = os.environ.get(name)
    os.environ[name] = value
    try:
        yield
    finally:
        if old is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = old


@pytest.fixture(scope="module")
def client():
    # Keep integration tests deterministic and fast: avoid background startup tasks.
    with _set_env("DISABLE_BACKGROUND_STARTUP_TASKS", "true"):
        with TestClient(app) as c:
            yield c


def test_root_is_public(client: TestClient):
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("message") == "Welcome to CookHero API!"
    assert "db_ready" in body


def test_protected_route_requires_auth(client: TestClient):
    resp = client.get("/api/v1/meta/capabilities")
    assert resp.status_code == 401
    assert resp.json().get("detail") == "需要登录"


def test_exempt_path_does_not_require_auth(client: TestClient):
    # login is exempt from auth middleware; GET is method-not-allowed, not 401.
    resp = client.get("/api/v1/auth/login")
    assert resp.status_code == 405


def test_readiness_gate_blocks_non_exempt_routes_when_db_not_ready(client: TestClient):
    original = getattr(app.state, "db_ready", True)
    try:
        app.state.db_ready = False
        resp = client.get("/api/v1/meta/capabilities")
        assert resp.status_code == 503
        assert resp.json().get("detail") == "服务初始化中，请稍后重试"
    finally:
        app.state.db_ready = original


def test_readiness_gate_allows_exempt_paths_when_db_not_ready(client: TestClient):
    original = getattr(app.state, "db_ready", True)
    try:
        app.state.db_ready = False
        resp = client.get("/api/v1/auth/login")
        assert resp.status_code == 405
    finally:
        app.state.db_ready = original


def test_options_preflight_is_not_blocked(client: TestClient):
    original = getattr(app.state, "db_ready", True)
    try:
        app.state.db_ready = False
        resp = client.options(
            "/api/v1/meta/capabilities",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization",
            },
        )
        assert resp.status_code in {200, 204}
        assert resp.headers.get("access-control-allow-origin")
    finally:
        app.state.db_ready = original


def test_rate_limit_middleware_short_circuits(monkeypatch, client: TestClient):
    from app.main import rate_limiter
    from app.security.audit import audit_logger

    called = {"audit": 0}

    async def fake_check(_request):
        return JSONResponse(status_code=429, content={"detail": "rate limited"})

    def fake_audit(**_kwargs):
        called["audit"] += 1

    monkeypatch.setattr(rate_limiter, "check_rate_limit", fake_check)
    monkeypatch.setattr(audit_logger, "rate_limit_exceeded", fake_audit)

    resp = client.get("/api/v1/meta/capabilities")
    assert resp.status_code == 429
    assert resp.json().get("detail") == "rate limited"
    assert called["audit"] == 1

