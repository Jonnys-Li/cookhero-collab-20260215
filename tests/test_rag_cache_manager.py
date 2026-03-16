from __future__ import annotations

import asyncio
import pickle

from langchain_core.documents import Document

from app.rag.cache.cache_manager import CacheManager


class FakeKeywordCache:
    def __init__(self):
        self.store: dict[str, bytes] = {}
        self.set_calls: list[tuple[str, int | None]] = []

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value: bytes, ttl_seconds: int | None = None) -> bool:
        self.store[key] = value
        self.set_calls.append((key, ttl_seconds))
        return True

    async def delete(self, key: str) -> bool:
        return self.store.pop(key, None) is not None

    async def clear(self, pattern: str | None = None) -> bool:
        self.store.clear()
        return True


class FakeVectorCache:
    def __init__(self):
        self.add_calls: list[tuple[str, list[float], bytes, int | None, str | None]] = []
        self.search_result = None

    async def add(
        self,
        key: str,
        embedding: list[float],
        payload,
        ttl_seconds: int | None = None,
        scope: str | None = None,
    ) -> bool:
        assert isinstance(payload, (bytes, bytearray))
        self.add_calls.append((key, list(embedding), bytes(payload), ttl_seconds, scope))
        return True

    async def search(self, embedding: list[float], threshold: float, scope: str | None = None):
        _ = (embedding, threshold, scope)
        return self.search_result

    async def clear(self) -> bool:
        return True


class FakeEmbeddings:
    def embed_query(self, text: str) -> list[float]:
        _ = text
        return [0.1, 0.2, 0.3]


def test_cache_manager_hash_and_key_format():
    manager = CacheManager(l2_enabled=False)
    key = manager._get_cache_key("recipes", "q1", scope="u1")
    assert key.startswith("rag:retrieval:recipes:u1:")
    assert len(key.split(":")[-1]) == 64  # sha256 hex


def test_cache_manager_get_l1_hit_returns_documents():
    manager = CacheManager(l2_enabled=False)
    manager.keyword_cache = FakeKeywordCache()

    docs = [Document(page_content="hello", metadata={"source": "s"})]
    key = manager._get_cache_key("recipes", "q1", scope=None)
    manager.keyword_cache.store[key] = pickle.dumps(docs)

    async def _run():
        got = await manager.get("recipes", "q1", scope=None)
        assert got is not None
        assert got[0].page_content == "hello"

    asyncio.run(_run())


def test_cache_manager_get_l2_hit_when_l1_misses():
    manager = CacheManager(l2_enabled=False)
    manager.keyword_cache = FakeKeywordCache()

    manager.l2_enabled = True
    manager.embeddings = FakeEmbeddings()
    manager.vector_cache = FakeVectorCache()

    docs = [Document(page_content="from-l2", metadata={"source": "s"})]
    manager.vector_cache.search_result = (pickle.dumps(docs), 0.99)

    async def _run():
        got = await manager.get("recipes", "q1", scope="global")
        assert got is not None
        assert got[0].page_content == "from-l2"

    asyncio.run(_run())


def test_cache_manager_set_writes_l1_and_l2():
    manager = CacheManager(l2_enabled=False)
    manager.keyword_cache = FakeKeywordCache()

    manager.l2_enabled = True
    manager.embeddings = FakeEmbeddings()
    manager.vector_cache = FakeVectorCache()

    docs = [Document(page_content="x", metadata={})]

    async def _run():
        ok = await manager.set("recipes", "q1", docs, scope="u1")
        assert ok is True
        assert manager.keyword_cache.set_calls
        assert manager.vector_cache.add_calls

    asyncio.run(_run())

