from __future__ import annotations

import sys
from types import SimpleNamespace

from app.config.rag_config import RAGConfig
from app.rag.embeddings.embedding_factory import (
    FallbackHashEmbeddings,
    get_embedding_model,
)


def test_fallback_hash_embeddings_is_deterministic_and_normalized():
    embeddings = FallbackHashEmbeddings(dimension=32)

    v1 = embeddings.embed_query("hello")
    v2 = embeddings.embed_query("hello")

    assert v1 == v2
    assert len(v1) == 32

    norm = sum(x * x for x in v1) ** 0.5
    assert abs(norm - 1.0) < 1e-6


def test_get_embedding_model_falls_back_when_hf_fails(monkeypatch):
    class FakeHFEmbeddings:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setitem(
        sys.modules,
        "langchain_huggingface",
        SimpleNamespace(HuggingFaceEmbeddings=FakeHFEmbeddings),
    )

    config = RAGConfig(embedding={"model_name": "fake"})
    model = get_embedding_model(config)
    assert isinstance(model, FallbackHashEmbeddings)


def test_get_embedding_model_returns_hf_instance_when_available(monkeypatch):
    class FakeHFEmbeddings:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    monkeypatch.setitem(
        sys.modules,
        "langchain_huggingface",
        SimpleNamespace(HuggingFaceEmbeddings=FakeHFEmbeddings),
    )

    config = RAGConfig(embedding={"model_name": "fake2"})
    model = get_embedding_model(config)
    assert isinstance(model, FakeHFEmbeddings)
    assert model.kwargs["model_name"] == "fake2"
    assert model.kwargs["model_kwargs"]["local_files_only"] is True

