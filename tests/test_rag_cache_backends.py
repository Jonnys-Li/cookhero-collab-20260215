from __future__ import annotations

import asyncio
import base64
from types import SimpleNamespace

from app.rag.cache.backends import MilvusVectorCache, RedisKeywordCache


class FakeRedisClient:
    def __init__(self):
        self.store: dict[str, bytes] = {}
        self.deleted: list[str] = []
        self.raise_on_get = False

    async def get(self, key: str):
        if self.raise_on_get:
            raise RuntimeError("boom")
        return self.store.get(key)

    async def setex(self, key: str, ttl_seconds: int, value: bytes):
        _ = ttl_seconds
        self.store[key] = value
        return True

    async def set(self, key: str, value: bytes):
        self.store[key] = value
        return True

    async def delete(self, *keys: str):
        deleted = 0
        for key in keys:
            if key in self.store:
                del self.store[key]
                deleted += 1
                self.deleted.append(key)
        return deleted

    async def scan(self, *, cursor: int, match: str, count: int):
        _ = (cursor, count)
        if match == "*":
            keys = list(self.store.keys())
        elif match.endswith("*"):
            prefix = match[:-1]
            keys = [k for k in self.store.keys() if k.startswith(prefix)]
        else:
            keys = [k for k in self.store.keys() if k == match]
        return 0, keys


def test_redis_keyword_cache_set_get_delete_and_clear():
    client = FakeRedisClient()
    cache = RedisKeywordCache(client)

    async def _run():
        assert await cache.set("a1", b"x", ttl_seconds=1) is True
        assert await cache.set("a2", b"y", ttl_seconds=None) is True
        assert await cache.set("b1", b"z", ttl_seconds=None) is True

        assert await cache.get("a1") == b"x"
        assert await cache.delete("a1") is True
        assert await cache.get("a1") is None

        assert await cache.clear(pattern="a*") is True
        assert await cache.get("a2") is None
        assert await cache.get("b1") == b"z"

    asyncio.run(_run())


def test_redis_keyword_cache_get_handles_errors_gracefully():
    client = FakeRedisClient()
    client.raise_on_get = True
    cache = RedisKeywordCache(client)

    async def _run():
        assert await cache.get("k") is None

    asyncio.run(_run())


def test_milvus_vector_cache_build_expr_and_early_returns():
    # Avoid touching Milvus by constructing the object without __init__.
    cache = MilvusVectorCache.__new__(MilvusVectorCache)
    cache._dimension = 3
    cache._collection = None

    expr = cache._build_valid_expr(scope="u1")
    assert "expires_at" in expr
    assert 'scope == "u1"' in expr

    async def _run():
        assert await cache.search([0.1, 0.2, 0.3], threshold=0.5, scope="u1") is None

        # Dimension mismatch (returns before touching collection).
        assert await cache.add("k1", [0.1, 0.2], b"x", ttl_seconds=1, scope="u1") is False

        # Zero vector (returns before touching collection).
        assert await cache.add("k2", [0.0, 0.0, 0.0], b"x", ttl_seconds=1, scope="u1") is False

    asyncio.run(_run())


def test_milvus_vector_cache_add_and_search_with_fake_collection():
    payload = b"hello"
    payload_b64 = base64.b64encode(payload).decode("utf-8")

    class FakeCollection:
        def __init__(self):
            self.deleted_exprs: list[str] = []
            self.inserted: list[list[list]] = []
            self.search_calls: list[dict] = []
            self.distance = 0.95
            self.payload_data = payload_b64

        def delete(self, *, expr: str):
            self.deleted_exprs.append(expr)

        def insert(self, data):
            self.inserted.append(data)

        def search(self, vectors, field, search_params, limit, *, expr: str, output_fields=None):
            self.search_calls.append(
                {
                    "vectors": vectors,
                    "field": field,
                    "search_params": search_params,
                    "limit": limit,
                    "expr": expr,
                    "output_fields": output_fields,
                }
            )
            hit = SimpleNamespace(distance=self.distance, entity={"payload_data": self.payload_data})
            return [[hit]]

    collection = FakeCollection()

    cache = MilvusVectorCache.__new__(MilvusVectorCache)
    cache._dimension = 3
    cache._collection = collection
    cache._search_params = {"metric_type": "IP", "params": {"nprobe": 16}}

    async def _run():
        ok = await cache.add(
            key="k1",
            embedding=[1.0, 0.0, 0.0],
            payload=payload,
            ttl_seconds=60,
            scope="u1",
        )
        assert ok is True
        assert any('cache_key == "k1"' in expr for expr in collection.deleted_exprs)
        assert collection.inserted

        result = await cache.search(
            embedding=[1.0, 0.0, 0.0],
            threshold=0.9,
            scope="u1",
        )
        assert result is not None
        cached_payload, similarity = result
        assert cached_payload == payload
        assert similarity == pytest.approx(0.95)

        # Similarity threshold should filter out low-distance hits.
        collection.distance = 0.1
        assert (
            await cache.search(
                embedding=[1.0, 0.0, 0.0],
                threshold=0.9,
                scope="u1",
            )
            is None
        )

        # Non-base64 payload should fall back to returning the raw string.
        collection.distance = 0.95
        collection.payload_data = "not-base64!!"
        result2 = await cache.search(
            embedding=[1.0, 0.0, 0.0],
            threshold=0.9,
            scope="u1",
        )
        assert result2 is not None
        assert result2[0] == "not-base64!!"

    import pytest

    asyncio.run(_run())
