from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.auth_service import AuthService


class FakeRedis:
    def __init__(self):
        self._values: dict[str, int | str] = {}
        self._ttl: dict[str, int] = {}

    async def ttl(self, key: str) -> int:
        return int(self._ttl.get(key, -1))

    async def incr(self, key: str) -> int:
        current = int(self._values.get(key, 0))
        current += 1
        self._values[key] = current
        return current

    async def expire(self, key: str, seconds: int) -> None:
        self._ttl[key] = int(seconds)

    async def setex(self, key: str, seconds: int, value: str) -> None:
        self._values[key] = value
        self._ttl[key] = int(seconds)

    async def delete(self, *keys: str) -> None:
        for key in keys:
            self._values.pop(key, None)
            self._ttl.pop(key, None)


def test_password_hash_roundtrip():
    service = AuthService(secret_key="test-secret")
    hashed = service._hash_password("p@ssw0rd")

    assert isinstance(hashed, str)
    assert service._verify_password("p@ssw0rd", hashed) is True
    assert service._verify_password("wrong", hashed) is False


def test_create_and_decode_access_token():
    service = AuthService(secret_key="test-secret")
    user = SimpleNamespace(username="alice", id="u1")

    token = service.create_access_token(user)
    decoded = service.decode_token(token)

    assert decoded == {"username": "alice", "user_id": "u1"}
    assert service.decode_token("not-a-jwt") is None


def test_login_lockout_disabled_without_redis(run):
    service = AuthService(secret_key="test-secret")

    locked, ttl = run(service.is_account_locked("alice"))
    assert locked is False
    assert ttl == 0

    attempts, now_locked = run(service.record_failed_attempt("alice"))
    assert attempts == 0
    assert now_locked is False

    # should not raise
    run(service.clear_failed_attempts("alice"))


def test_login_lockout_with_redis(run):
    service = AuthService(secret_key="test-secret")
    service.max_failed_attempts = 2
    service.lockout_minutes = 1

    redis = FakeRedis()
    service.set_redis(redis)  # type: ignore[arg-type]

    attempts, now_locked = run(service.record_failed_attempt("alice"))
    assert attempts == 1
    assert now_locked is False

    attempts, now_locked = run(service.record_failed_attempt("alice"))
    assert attempts == 2
    assert now_locked is True

    locked, ttl = run(service.is_account_locked("alice"))
    assert locked is True
    assert ttl > 0

    run(service.clear_failed_attempts("alice"))
    locked, ttl = run(service.is_account_locked("alice"))
    assert locked is False
    assert ttl == 0


def test_login_lockout_key_helpers_are_stable(run):
    service = AuthService(secret_key="test-secret")
    redis = FakeRedis()
    service.set_redis(redis)  # type: ignore[arg-type]

    failed_key = run(service._get_failed_attempts_key("alice"))
    lock_key = run(service._get_lockout_key("alice"))
    assert failed_key.endswith(":alice")
    assert lock_key.endswith(":alice")

