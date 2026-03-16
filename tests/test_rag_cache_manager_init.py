from __future__ import annotations

import importlib
from types import SimpleNamespace


def test_cache_manager_init_enables_l1_and_l2_when_configured(monkeypatch):
    cm_mod = importlib.import_module("app.rag.cache.cache_manager")

    class FakeRedis:
        def __init__(self, **_kwargs):
            pass

    class FakeEmbeddings:
        def embed_query(self, _text: str):
            return [0.1, 0.2, 0.3]

    created = {}

    class FakeMilvusVectorCache:
        def __init__(self, **kwargs):
            created.update(kwargs)

    monkeypatch.setattr(cm_mod.redis, "Redis", lambda **kwargs: FakeRedis(**kwargs))
    monkeypatch.setattr(cm_mod, "MilvusVectorCache", FakeMilvusVectorCache)

    manager = cm_mod.CacheManager(
        redis_host="rh",
        redis_port=1,
        l2_enabled=True,
        embeddings=FakeEmbeddings(),
        vector_host="vh",
        vector_port=2,
        vector_collection="coll",
        vector_user="u",
        vector_password="p",
        vector_secure=True,
    )

    assert manager.keyword_cache is not None
    assert manager.l2_enabled is True
    assert manager.vector_cache is not None
    assert manager._embedding_dimension == 3
    assert created["host"] == "vh"
    assert created["port"] == 2
    assert created["collection_name"] == "coll"
    assert created["dimension"] == 3


def test_cache_manager_init_disables_l2_when_embeddings_missing(monkeypatch):
    cm_mod = importlib.import_module("app.rag.cache.cache_manager")

    monkeypatch.setattr(cm_mod.redis, "Redis", lambda **_kwargs: SimpleNamespace())
    manager = cm_mod.CacheManager(l2_enabled=True, embeddings=None)
    assert manager.l2_enabled is False


def test_cache_manager_init_disables_l2_when_dimension_inference_fails(monkeypatch):
    cm_mod = importlib.import_module("app.rag.cache.cache_manager")

    class BadEmbeddings:
        def embed_query(self, _text: str):
            raise RuntimeError("boom")

    monkeypatch.setattr(cm_mod.redis, "Redis", lambda **_kwargs: SimpleNamespace())
    manager = cm_mod.CacheManager(l2_enabled=True, embeddings=BadEmbeddings())
    assert manager.l2_enabled is False


def test_cache_manager_init_disables_l2_when_milvus_init_fails(monkeypatch):
    cm_mod = importlib.import_module("app.rag.cache.cache_manager")

    class FakeEmbeddings:
        def embed_query(self, _text: str):
            return [0.1, 0.2, 0.3]

    def _raise(**_kwargs):
        raise RuntimeError("milvus down")

    monkeypatch.setattr(cm_mod.redis, "Redis", lambda **_kwargs: SimpleNamespace())
    monkeypatch.setattr(cm_mod, "MilvusVectorCache", _raise)
    manager = cm_mod.CacheManager(l2_enabled=True, embeddings=FakeEmbeddings())
    assert manager.l2_enabled is False
    assert manager.vector_cache is None

