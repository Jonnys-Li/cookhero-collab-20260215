from __future__ import annotations

from types import SimpleNamespace

import pytest
from langchain_core.documents import Document

from app.config.database_config import MilvusConfig
from app.rag.vector_stores import vector_store_factory as vsf


def test_is_local_milvus_lite_recognizes_path_hosts():
    assert vsf._is_local_milvus_lite("/tmp/milvus.db")
    assert vsf._is_local_milvus_lite("./milvus.db")
    assert vsf._is_local_milvus_lite("foo.db")
    assert not vsf._is_local_milvus_lite("localhost")


def test_build_vector_store_kwargs_hybrid_vs_dense():
    dense = vsf._build_vector_store_kwargs(
        collection_name="c1",
        connection_args={"uri": "/tmp/milvus.db"},
        use_hybrid_search=False,
    )
    assert dense["collection_name"] == "c1"
    assert dense["connection_args"] == {"uri": "/tmp/milvus.db"}
    assert "vector_field" not in dense
    assert "builtin_function" not in dense
    assert dense["index_params"]["index_type"] == "FLAT"

    hybrid = vsf._build_vector_store_kwargs(
        collection_name="c2",
        connection_args={"host": "127.0.0.1", "port": 19530},
        use_hybrid_search=True,
    )
    assert hybrid["collection_name"] == "c2"
    assert hybrid["vector_field"] == ["dense", "sparse"]
    assert "builtin_function" in hybrid


def test_get_vector_store_creates_missing_collection_with_placeholder(monkeypatch):
    connected: set[str] = set()

    def fake_connect(*, alias: str, **_kwargs):
        connected.add(alias)

    def fake_has_connection(alias: str) -> bool:
        return alias in connected

    def fake_disconnect(alias: str):
        connected.discard(alias)

    # Simulate "no existing collection"
    def fake_has_collection(_name: str, *, using: str):
        assert using == "default"
        return False

    drop_calls: list[str] = []

    def fake_drop_collection(name: str, *, using: str):
        drop_calls.append(f"{using}:{name}")
        return True

    from_docs_calls: list[dict] = []

    class FakeMilvus:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs
            self.col = SimpleNamespace(delete=lambda **_kw: None)

        @classmethod
        def from_documents(cls, documents, embedding, **kwargs):
            from_docs_calls.append(
                {
                    "documents": list(documents),
                    "embedding": embedding,
                    "kwargs": dict(kwargs),
                }
            )
            return cls(embedding_function=embedding, **kwargs)

    monkeypatch.setattr(vsf.connections, "connect", fake_connect)
    monkeypatch.setattr(vsf.connections, "disconnect", fake_disconnect)
    monkeypatch.setattr(vsf.connections, "has_connection", fake_has_connection)
    monkeypatch.setattr(vsf.utility, "has_collection", fake_has_collection)
    monkeypatch.setattr(vsf.utility, "drop_collection", fake_drop_collection)
    monkeypatch.setattr(vsf, "Milvus", FakeMilvus)

    milvus_config = MilvusConfig(host="/tmp/milvus.db", port=19530)
    fake_embeddings = object()

    store = vsf.get_vector_store(
        milvus_config=milvus_config,
        collection_name="test_collection",
        embeddings=fake_embeddings,
        chunks=[],  # forces placeholder path
        force_rebuild=False,
    )

    assert isinstance(store, FakeMilvus)
    assert drop_calls == []
    assert from_docs_calls, "Expected Milvus.from_documents to be used for creation"
    docs = from_docs_calls[0]["documents"]
    assert len(docs) == 1
    assert docs[0].page_content == "__placeholder__"


def test_get_vector_store_connects_existing_collection(monkeypatch):
    connected: set[str] = set()

    def fake_connect(*, alias: str, **_kwargs):
        connected.add(alias)

    def fake_has_connection(alias: str) -> bool:
        return alias in connected

    def fake_disconnect(alias: str):
        connected.discard(alias)

    def fake_has_collection(_name: str, *, using: str):
        return True

    class FakeMilvus:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        @classmethod
        def from_documents(cls, *_args, **_kwargs):  # pragma: no cover
            raise AssertionError("from_documents should not be called for existing collections")

    monkeypatch.setattr(vsf.connections, "connect", fake_connect)
    monkeypatch.setattr(vsf.connections, "disconnect", fake_disconnect)
    monkeypatch.setattr(vsf.connections, "has_connection", fake_has_connection)
    monkeypatch.setattr(vsf.utility, "has_collection", fake_has_collection)
    monkeypatch.setattr(vsf, "Milvus", FakeMilvus)

    milvus_config = MilvusConfig(host="127.0.0.1", port=19530)
    fake_embeddings = object()

    store = vsf.get_vector_store(
        milvus_config=milvus_config,
        collection_name="existing_collection",
        embeddings=fake_embeddings,
        chunks=[Document(page_content="ignored", metadata={})],
        force_rebuild=False,
    )

    assert isinstance(store, FakeMilvus)
    assert store.kwargs.get("embedding_function") is fake_embeddings


def test_get_vector_store_force_rebuild_drops_collection(monkeypatch):
    connected: set[str] = set()

    def fake_connect(*, alias: str, **_kwargs):
        connected.add(alias)

    def fake_has_connection(alias: str) -> bool:
        return alias in connected

    def fake_disconnect(alias: str):
        connected.discard(alias)

    exists = {"value": True}

    def fake_has_collection(_name: str, *, using: str):
        return bool(exists["value"])

    drop_calls: list[str] = []

    def fake_drop_collection(name: str, *, using: str):
        drop_calls.append(f"{using}:{name}")
        exists["value"] = False
        return True

    class FakeMilvus:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs
            self.col = SimpleNamespace(delete=lambda **_kw: None)

        @classmethod
        def from_documents(cls, documents, embedding, **kwargs):
            return cls(embedding_function=embedding, **kwargs)

    monkeypatch.setattr(vsf.connections, "connect", fake_connect)
    monkeypatch.setattr(vsf.connections, "disconnect", fake_disconnect)
    monkeypatch.setattr(vsf.connections, "has_connection", fake_has_connection)
    monkeypatch.setattr(vsf.utility, "has_collection", fake_has_collection)
    monkeypatch.setattr(vsf.utility, "drop_collection", fake_drop_collection)
    monkeypatch.setattr(vsf, "Milvus", FakeMilvus)

    milvus_config = MilvusConfig(host="127.0.0.1", port=19530)
    fake_embeddings = object()

    store = vsf.get_vector_store(
        milvus_config=milvus_config,
        collection_name="rebuild_collection",
        embeddings=fake_embeddings,
        chunks=[],  # use placeholder path
        force_rebuild=True,
    )

    assert isinstance(store, FakeMilvus)
    assert drop_calls == ["default:rebuild_collection"]

