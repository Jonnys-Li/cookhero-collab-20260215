from __future__ import annotations

import pytest


def test_rag_lazy_exports_resolve_known_symbols():
    import app.rag as rag

    # These attributes are exposed via __getattr__ and should resolve lazily.
    assert rag.CacheManager is not None
    assert rag.document_processor is not None
    assert rag.RetrievalOptimizationModule is not None
    assert rag.GenerationIntegrationModule is not None
    assert rag.MetadataFilterExtractor is not None


def test_rag_lazy_exports_unknown_symbol_raises():
    import app.rag as rag

    with pytest.raises(AttributeError):
        _ = rag.DOES_NOT_EXIST  # type: ignore[attr-defined]

