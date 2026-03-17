from __future__ import annotations

import os
from contextlib import contextmanager

import pytest
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


def test_openapi_includes_api_v1_health(client: TestClient):
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    body = resp.json()
    paths = body.get("paths") or {}
    assert "/api/v1/health" in paths

