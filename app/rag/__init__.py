# app/rag/__init__.py
"""
RAG (Retrieval-Augmented Generation) module for CookHero.

This module provides the core RAG pipeline functionality including:
- Document processing and chunking
- Vector embeddings and storage
- Retrieval optimization
- Caching for performance
- Reranking for relevance
"""

from __future__ import annotations

from typing import Any

__all__ = [
    # Cache
    "CacheManager",
    # Pipeline
    "document_processor",
    "RetrievalOptimizationModule",
    "GenerationIntegrationModule",
    "MetadataFilterExtractor",
]


def __getattr__(name: str) -> Any:
    """
    Lazy exports to avoid import-time dependency failures.

    RAG submodules may require optional heavy dependencies (e.g. langchain-milvus).
    Keep package import lightweight so backend can still boot in degraded mode.
    """
    if name == "CacheManager":
        from app.rag.cache import CacheManager

        return CacheManager
    if name == "document_processor":
        from app.rag.pipeline.document_processor import document_processor

        return document_processor
    if name == "RetrievalOptimizationModule":
        from app.rag.pipeline.retrieval import RetrievalOptimizationModule

        return RetrievalOptimizationModule
    if name == "GenerationIntegrationModule":
        from app.rag.pipeline.generation import GenerationIntegrationModule

        return GenerationIntegrationModule
    if name == "MetadataFilterExtractor":
        from app.rag.pipeline.metadata_filter import MetadataFilterExtractor

        return MetadataFilterExtractor

    raise AttributeError(f"module 'app.rag' has no attribute '{name}'")
