from __future__ import annotations

from types import SimpleNamespace

from langchain_core.documents import Document

from app.config.database_config import MilvusConfig
import app.rag.vector_stores.vector_store_factory as vs_factory


class FakeMilvus:
    init_calls: list[dict] = []
    from_documents_calls: list[dict] = []

    def __init__(self, *args, **kwargs):
        _ = args
        FakeMilvus.init_calls.append(kwargs)
        self.kwargs = kwargs
        self.deleted_expr = None

        def _delete(*_args, **_kwargs):
            self.deleted_expr = _kwargs.get("expr") if _kwargs else None

        self.col = SimpleNamespace(delete=_delete)

    @classmethod
    def from_documents(cls, *, documents, embedding, **kwargs):
        cls.from_documents_calls.append(
            {"documents": list(documents), "embedding": embedding, "kwargs": kwargs}
        )
        return cls(embedding_function=embedding, **kwargs)


def test_is_local_milvus_lite_detects_paths():
    assert vs_factory._is_local_milvus_lite("/tmp/milvus.db") is True
    assert vs_factory._is_local_milvus_lite("./milvus.db") is True
    assert vs_factory._is_local_milvus_lite("localhost") is False


def test_build_vector_store_kwargs_hybrid_and_dense_only():
    hybrid = vs_factory._build_vector_store_kwargs(
        collection_name="c",
        connection_args={"host": "h", "port": 1},
        use_hybrid_search=True,
    )
    assert hybrid["vector_field"] == ["dense", "sparse"]
    assert "builtin_function" in hybrid

    dense = vs_factory._build_vector_store_kwargs(
        collection_name="c",
        connection_args={"uri": "/tmp/x.db"},
        use_hybrid_search=False,
    )
    assert "index_params" in dense
    assert "vector_field" not in dense


def test_get_vector_store_creates_collection_when_missing(monkeypatch):
    FakeMilvus.init_calls = []
    FakeMilvus.from_documents_calls = []

    state = {"connected": False}

    def connect(*_args, **_kwargs):
        state["connected"] = True

    def has_connection(_alias: str):
        return state["connected"]

    def disconnect(_alias: str):
        state["connected"] = False

    monkeypatch.setattr(vs_factory.connections, "connect", connect)
    monkeypatch.setattr(vs_factory.connections, "has_connection", has_connection)
    monkeypatch.setattr(vs_factory.connections, "disconnect", disconnect)

    monkeypatch.setattr(vs_factory.utility, "has_collection", lambda *_a, **_k: False)
    monkeypatch.setattr(vs_factory, "Milvus", FakeMilvus)

    milvus_config = MilvusConfig(host="localhost", port=19530)
    chunks = [Document(page_content="x", metadata={})]
    embeddings = object()

    store = vs_factory.get_vector_store(
        milvus_config=milvus_config,
        collection_name="c1",
        embeddings=embeddings,
        chunks=chunks,
        force_rebuild=False,
    )
    assert isinstance(store, FakeMilvus)
    assert FakeMilvus.from_documents_calls
    assert state["connected"] is False


def test_get_vector_store_creates_placeholder_when_no_chunks(monkeypatch):
    FakeMilvus.init_calls = []
    FakeMilvus.from_documents_calls = []

    state = {"connected": False}

    monkeypatch.setattr(vs_factory.connections, "connect", lambda *_a, **_k: state.__setitem__("connected", True))
    monkeypatch.setattr(vs_factory.connections, "has_connection", lambda _alias: state["connected"])
    monkeypatch.setattr(vs_factory.connections, "disconnect", lambda *_a, **_k: state.__setitem__("connected", False))

    monkeypatch.setattr(vs_factory.utility, "has_collection", lambda *_a, **_k: False)
    monkeypatch.setattr(vs_factory, "Milvus", FakeMilvus)

    milvus_config = MilvusConfig(host="localhost", port=19530)
    embeddings = object()

    store = vs_factory.get_vector_store(
        milvus_config=milvus_config,
        collection_name="c2",
        embeddings=embeddings,
        chunks=[],
        force_rebuild=False,
    )
    assert isinstance(store, FakeMilvus)
    assert store.deleted_expr == 'text == "__placeholder__"'
    assert state["connected"] is False


def test_get_vector_store_connects_to_existing_collection(monkeypatch):
    FakeMilvus.init_calls = []
    FakeMilvus.from_documents_calls = []

    state = {"connected": False}

    monkeypatch.setattr(vs_factory.connections, "connect", lambda *_a, **_k: state.__setitem__("connected", True))
    monkeypatch.setattr(vs_factory.connections, "has_connection", lambda _alias: state["connected"])
    monkeypatch.setattr(vs_factory.connections, "disconnect", lambda *_a, **_k: state.__setitem__("connected", False))

    monkeypatch.setattr(vs_factory.utility, "has_collection", lambda *_a, **_k: True)
    monkeypatch.setattr(vs_factory, "Milvus", FakeMilvus)

    milvus_config = MilvusConfig(host="localhost", port=19530)
    embeddings = object()

    store = vs_factory.get_vector_store(
        milvus_config=milvus_config,
        collection_name="c3",
        embeddings=embeddings,
        chunks=[],
        force_rebuild=False,
    )
    assert isinstance(store, FakeMilvus)
    assert FakeMilvus.init_calls
    assert FakeMilvus.from_documents_calls == []
    assert state["connected"] is False

