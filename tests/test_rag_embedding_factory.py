from __future__ import annotations

import math

from app.config.rag_config import RAGConfig
from app.rag.embeddings.embedding_factory import (
    FallbackHashEmbeddings,
    get_embedding_model,
)


def _l2_norm(values: list[float]) -> float:
    return math.sqrt(sum(v * v for v in values))


def test_fallback_hash_embeddings_is_deterministic_and_normalized():
    emb = FallbackHashEmbeddings(dimension=32)
    v1 = emb.embed_query("hello")
    v2 = emb.embed_query("hello")
    v3 = emb.embed_query("world")

    assert len(v1) == 32
    assert v1 == v2
    # Different inputs should almost always produce different vectors.
    assert v1 != v3

    assert abs(_l2_norm(v1) - 1.0) < 1e-6


def test_fallback_hash_embeddings_embed_documents_shape():
    emb = FallbackHashEmbeddings(dimension=8)
    vectors = emb.embed_documents(["a", "b", "c"])
    assert len(vectors) == 3
    assert all(len(v) == 8 for v in vectors)


def test_get_embedding_model_falls_back_when_local_model_unavailable(monkeypatch):
    # Force the HuggingFaceEmbeddings constructor to fail so we deterministically
    # exercise the fallback path without relying on local model files.
    import langchain_huggingface

    def _boom(*_args, **_kwargs):
        raise RuntimeError("no local model files")

    monkeypatch.setattr(langchain_huggingface, "HuggingFaceEmbeddings", _boom)

    model = get_embedding_model(RAGConfig())
    assert isinstance(model, FallbackHashEmbeddings)

