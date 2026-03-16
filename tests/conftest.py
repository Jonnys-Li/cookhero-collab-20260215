import asyncio
from types import SimpleNamespace

import pytest


@pytest.fixture
def run():
    """Small helper to run async endpoint/service calls from sync tests."""

    def _run(coro):
        return asyncio.run(coro)

    return _run


@pytest.fixture
def build_request():
    """Build a minimal request-like object with `request.state.user_id`."""

    def _build_request(user_id: str = "u1"):
        return SimpleNamespace(state=SimpleNamespace(user_id=user_id))

    return _build_request

