from __future__ import annotations

import asyncio

import pytest


def test_rag_service_degraded_mode_sets_dependency_error(monkeypatch):
    import app.services.rag_service as rag_mod
    from app.services.rag_service import RAGService

    # Ensure a fresh singleton for this test (and restore afterwards).
    monkeypatch.setattr(RAGService, "_instance", None, raising=False)
    monkeypatch.setattr(rag_mod, "_rag_service_instance", None, raising=False)

    import app.rag.embeddings.embedding_factory as embedding_factory

    def _raise(_config):
        raise RuntimeError("missing-deps")

    monkeypatch.setattr(embedding_factory, "get_embedding_model", _raise)

    service = RAGService()
    assert service.embeddings is None
    assert service._dependency_error is not None
    assert service.retrieval_modules == {}

    async def _run():
        with pytest.raises(RuntimeError) as exc:
            await service.retrieve("q")
        assert "dependencies unavailable" in str(exc.value)

    asyncio.run(_run())

