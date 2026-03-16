from __future__ import annotations

from types import SimpleNamespace

from app.security.middleware.rate_limiter import RateLimitConfig, RateLimiter


def _make_request(path: str, *, client_ip: str = "1.2.3.4", headers: dict | None = None):
    return SimpleNamespace(
        url=SimpleNamespace(path=path),
        headers=headers or {},
        client=SimpleNamespace(host=client_ip),
        state=SimpleNamespace(),
        method="GET",
    )


def test_get_limit_for_path():
    limiter = RateLimiter(
        redis_client=None,
        config=RateLimitConfig(
            global_per_minute=100,
            login_per_minute=5,
            conversation_per_minute=30,
            enabled=True,
        ),
    )
    assert limiter._get_limit_for_path("/api/v1/auth/login") == 5
    assert limiter._get_limit_for_path("/api/v1/auth/register") == 5
    assert limiter._get_limit_for_path("/api/v1/conversation") == 30
    assert limiter._get_limit_for_path("/api/v1/health") == 100


def test_check_rate_limit_skips_docs_and_root(run):
    limiter = RateLimiter(redis_client=None, config=RateLimitConfig(enabled=True))

    async def _run():
        assert await limiter.check_rate_limit(_make_request("/")) is None
        assert await limiter.check_rate_limit(_make_request("/docs")) is None
        assert await limiter.check_rate_limit(_make_request("/openapi.json")) is None

    run(_run())


def test_check_rate_limit_allows_when_redis_unavailable_and_sets_state(run):
    limiter = RateLimiter(
        redis_client=None,
        config=RateLimitConfig(global_per_minute=2, conversation_per_minute=2, enabled=True),
    )
    req = _make_request("/api/v1/conversation")

    async def _run():
        resp = await limiter.check_rate_limit(req)
        assert resp is None
        assert req.state.rate_limit_limit == 2
        assert req.state.rate_limit_remaining == 2

    run(_run())


def test_check_rate_limit_blocks_when_exceeded(run):
    class FakeRedis:
        def __init__(self):
            self.counts: dict[str, int] = {}

        async def incr(self, key: str) -> int:
            self.counts[key] = self.counts.get(key, 0) + 1
            return self.counts[key]

        async def expire(self, _key: str, _ttl: int) -> None:
            return None

    limiter = RateLimiter(
        redis_client=FakeRedis(),
        config=RateLimitConfig(
            global_per_minute=100,
            login_per_minute=100,
            conversation_per_minute=1,
            enabled=True,
        ),
    )
    req = _make_request("/api/v1/conversation")

    async def _run():
        assert await limiter.check_rate_limit(req) is None
        resp = await limiter.check_rate_limit(req)
        assert resp is not None
        assert resp.status_code == 429
        assert resp.headers.get("X-RateLimit-Remaining") == "0"

    run(_run())


def test_check_limit_is_fail_open_on_redis_exception(run):
    class FakeRedis:
        async def incr(self, _key: str) -> int:
            raise RuntimeError("redis down")

        async def expire(self, _key: str, _ttl: int) -> None:
            return None

    limiter = RateLimiter(redis_client=FakeRedis(), config=RateLimitConfig(enabled=True))

    async def _run():
        allowed, current, remaining = await limiter._check_limit("k", limit=1)
        assert allowed is True
        assert current == 0
        assert remaining == 1

    run(_run())
