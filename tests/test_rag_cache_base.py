from __future__ import annotations

import asyncio

from app.rag.cache.base import KeywordCacheBackend, VectorCacheBackend


def test_cache_backend_abstract_base_pass_through_lines_are_executable():
    # These base classes define abstract methods with `pass`. We exercise them via
    # super() calls to ensure the module stays fully covered and import-safe.

    class KeywordImpl(KeywordCacheBackend):
        async def get(self, key: str):
            return await super().get(key)

        async def set(self, key: str, value: bytes, ttl_seconds: int | None = None) -> bool:
            _ = (key, value, ttl_seconds)
            return await super().set(key, value, ttl_seconds=ttl_seconds)

        async def delete(self, key: str) -> bool:
            return await super().delete(key)

        async def clear(self, pattern: str | None = None) -> bool:
            return await super().clear(pattern=pattern)

    class VectorImpl(VectorCacheBackend):
        async def add(self, key: str, embedding: list[float], payload, ttl_seconds: int | None = None, scope: str | None = None) -> bool:
            _ = (key, embedding, payload, ttl_seconds, scope)
            return await super().add(key, embedding, payload, ttl_seconds=ttl_seconds, scope=scope)

        async def search(self, embedding: list[float], threshold: float, scope: str | None = None):
            _ = (embedding, threshold, scope)
            return await super().search(embedding, threshold, scope=scope)

        async def clear(self) -> bool:
            return await super().clear()

    async def _run():
        k = KeywordImpl()
        assert await k.get("k") is None
        assert await k.set("k", b"x", ttl_seconds=1) is None
        assert await k.delete("k") is None
        assert await k.clear(pattern="*") is None

        v = VectorImpl()
        assert await v.add("k", [0.1], b"x") is None
        assert await v.search([0.1], 0.0) is None
        assert await v.clear() is None

    asyncio.run(_run())

