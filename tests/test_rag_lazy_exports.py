from __future__ import annotations

import pytest


def test_rag_package_lazy_exports():
    import app.rag as rag

    assert rag.CacheManager is not None
    assert rag.document_processor is not None
    assert rag.RetrievalOptimizationModule is not None
    assert rag.GenerationIntegrationModule is not None
    assert rag.MetadataFilterExtractor is not None

    with pytest.raises(AttributeError):
        _ = getattr(rag, "does_not_exist")

