"""RAG pipeline workflow helpers for query planning, retrieval, and assembly."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, final

from langchain_core.documents import Document

from app.rag.cache import CacheManager
from app.rag.pipeline.metadata_filter import MetadataFilterExtractor
from app.rag.pipeline.retrieval import RetrievalOptimizationModule
from app.rag.pipeline.generation import GenerationIntegrationModule
from app.rag.data_sources.base import BaseDataSource

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class QueryPlan:
    original_query: str
    rewritten_query: str
    metadata_expression: Optional[str]
    cached_response: Optional[str]


class QueryPlanner:
    """Handles query rewriting, metadata expression generation, and cache lookup."""

    def __init__(
        self,
        generation_module: GenerationIntegrationModule,
        metadata_filter_extractor: MetadataFilterExtractor,
        cache_manager: CacheManager | None,
    ) -> None:
        self._generation_module = generation_module
        self._metadata_filter_extractor = metadata_filter_extractor
        self._cache_manager = cache_manager

    def prepare(self, query: str, metadata_catalog: Dict[str, Dict[str, List[str]]]) -> QueryPlan:
        rewritten_query = self._generation_module.rewrite_query(query)
        metadata_expression = self._metadata_filter_extractor.build_filter_expression(
            query,
            metadata_catalog,
        )
        return QueryPlan(
            original_query=query,
            rewritten_query=rewritten_query,
            metadata_expression=metadata_expression,
            cached_response=None,  # Response caching removed - only cache retrieval results
        )


class RetrievalExecutor:
    """Coordinates retrieval across multiple sources with caching."""

    def __init__(
        self,
        retrieval_modules: Dict[str, RetrievalOptimizationModule],
        cache_manager: CacheManager | None,
    ) -> None:
        self._retrieval_modules = retrieval_modules
        self._cache_manager = cache_manager

    def retrieve(
        self,
        rewritten_query: str,
        top_k: int,
        use_intelligent_ranker: bool,
        metadata_expression: Optional[str],
    ) -> List[Document]:
        all_retrieved_docs: List[Document] = []
        for name, module in self._retrieval_modules.items():
            docs = self._retrieve_from_single_source(
                source_name=name,
                retrieval_module=module,
                rewritten_query=rewritten_query,
                top_k=top_k,
                use_intelligent_ranker=use_intelligent_ranker,
                metadata_expression=metadata_expression,
            )
            all_retrieved_docs.extend(docs)
        logger.info("--- Aggregated %d documents from all sources ---", len(all_retrieved_docs))
        return all_retrieved_docs

    def _retrieve_from_single_source(
        self,
        source_name: str,
        retrieval_module: RetrievalOptimizationModule,
        rewritten_query: str,
        top_k: int,
        use_intelligent_ranker: bool,
        metadata_expression: Optional[str],
    ) -> List[Document]:
        logger.info("Retrieving from source: %s", source_name)
        cached_docs: Optional[List[Document]] = None
        if self._cache_manager:
            cached_docs = self._cache_manager.get(
                source_name,
                rewritten_query,
            )
        if cached_docs:
            logger.info(
                "Using cached retrieval results for source '%s': %d documents",
                source_name,
                len(cached_docs),
            )
            for doc in cached_docs:
                if "retrieval_score" not in doc.metadata:
                    doc.metadata["retrieval_score"] = 1.0
                doc.metadata["data_source"] = source_name
            return cached_docs

        ranker_type = ranker_weights = None
        if use_intelligent_ranker:
            ranker_type, ranker_weights = retrieval_module.intelligent_ranker_selection(rewritten_query)

        try:
            retrieved_docs, retrieved_scores = retrieval_module.hybrid_search(
                rewritten_query,
                top_k=top_k,
                ranker_type=ranker_type,
                ranker_weights=ranker_weights,
                expr=metadata_expression,
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Error during retrieval from source '%s': %s", source_name, exc)
            return []

        for doc, score in zip(retrieved_docs, retrieved_scores):
            existing_source = doc.metadata.get("data_source")
            if existing_source and existing_source != source_name:
                logger.warning(
                    "Data source mismatch detected (metadata=%s, expected=%s). Overriding.",
                    existing_source,
                    source_name,
                )
            doc.metadata["data_source"] = existing_source or source_name
            doc.metadata["retrieval_score"] = score

        # deuplicate documents based on parent_id and keep the highest score
        unique_docs: Dict[Optional[str], Document] = {}
        for doc in retrieved_docs:
            parent_id = doc.metadata.get("parent_id")
            if parent_id not in unique_docs:
                unique_docs[parent_id] = doc
            else:
                if doc.metadata["retrieval_score"] > unique_docs[parent_id].metadata["retrieval_score"]:
                    unique_docs[parent_id] = doc
        final_docs = list(unique_docs.values())
        final_docs.sort(key=lambda d: d.metadata.get("retrieval_score", 0.0), reverse=True)

        # Log each document with its score
        for i, doc in enumerate(final_docs):
            score = doc.metadata.get("retrieval_score", 0.0)
            logger.info("=" * 60)
            logger.info(f"Final Rank #{i+1} | Score: {score:.4f} | Doc ID: {doc.id}")
            logger.info(f"Metadata: {doc.metadata}")
            logger.info(f"Content preview: {doc.page_content[:10]}...")

        if self._cache_manager:
            self._cache_manager.set(
                source_name,
                rewritten_query,
                final_docs,
            )

        return final_docs


class DocumentPostProcessor:
    """Restores parent documents and removes duplicates."""

    def __init__(self, data_sources: Dict[str, BaseDataSource]) -> None:
        self._data_sources = data_sources

    def process(self, retrieved_docs: List[Document]) -> List[Document]:
        parent_docs = self._restore_parent_documents(retrieved_docs)
        return parent_docs

    def _restore_parent_documents(self, retrieved_docs: List[Document]) -> List[Document]:
        docs_by_source: Dict[str, List[Document]] = {}
        for doc in retrieved_docs:
            source_name = doc.metadata.get("data_source")
            if not source_name or source_name not in self._data_sources:
                continue
            docs_by_source.setdefault(source_name, []).append(doc)

        parent_docs: List[Document] = []
        for source_name, docs in docs_by_source.items():
            data_source = self._data_sources[source_name]
            parent_docs.extend(data_source.post_process_retrieval(docs))
        return parent_docs


class ContextBuilder:
    """Extracts plain-text context strings from documents."""

    @staticmethod
    def build(documents: List[Document]) -> List[str]:
        return [doc.page_content for doc in documents]


class ResponseGenerator:
    """Handles response generation."""

    def __init__(
        self,
        generation_module: GenerationIntegrationModule,
        cache_manager: CacheManager | None,
    ) -> None:
        self._generation_module = generation_module
        # cache_manager kept for interface compatibility but no longer used for response caching

    def generate(self, rewritten_query: str, context_parts: List[str], stream: bool):
        return self._generation_module.generate_response(
            query=rewritten_query,
            context_docs=context_parts,
            stream=stream,
        )