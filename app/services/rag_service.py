# app/services/rag_service.py
"""
RAG Service - Orchestrates the RAG pipeline for knowledge retrieval and response generation.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Generator, List, Optional

from langchain_core.documents import Document

from app.config import (
    DefaultRAGConfig,
    LLMOverrideConfig,
    LLMProviderConfig,
    RAGConfig,
    settings,
)
from app.rag.data_sources.base import BaseDataSource
from app.rag.data_sources.howtocook_data_source import HowToCookDataSource
from app.rag.data_sources.tips_data_source import TipsDataSource
from app.rag.embeddings.embedding_factory import get_embedding_model
from app.rag.vector_stores.vector_store_factory import get_vector_store
from app.rag.pipeline.retrieval import RetrievalOptimizationModule
from app.rag.pipeline.generation import GenerationIntegrationModule
from app.rag.pipeline.metadata_filter import MetadataFilterExtractor
from app.rag.pipeline.workflow import (
    ContextBuilder,
    DocumentPostProcessor,
    QueryPlanner,
    RetrievalExecutor,
    ResponseGenerator,
)
from app.rag.rerankers.base import BaseReranker
from app.rag.cache import CacheManager

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    """
    Result of RAG retrieval operation.
    Contains the rewritten query and retrieved context.
    """
    original_query: str
    rewritten_query: str
    context: str
    documents: List[Document]
    sources: List[Dict]


class RAGService:
    """
    Orchestrates the entire RAG pipeline, supporting multiple data sources
    and query routing.
    
    Provides two main interfaces:
    1. retrieve() - Only performs query rewriting and retrieval, returns context
    2. ask_with_generation() - Full RAG + LLM generation pipeline
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(RAGService, cls).__new__(cls)
        return cls._instance

    def __init__(self, config: RAGConfig | None = None):
        if hasattr(self, '_initialized') and self._initialized:
            return

        logger.info("Initializing RAGService for the first time...")
        self.config = config or DefaultRAGConfig
        self.llm_config = self._resolve_llm_config(settings.llm, self.config.llm_override)
        
        self.data_sources: Dict[str, BaseDataSource] = {}
        self.retrieval_modules: Dict[str, RetrievalOptimizationModule] = {}
        self.reranker: BaseReranker | None = None
        self.metadata_catalog: Dict[str, Dict[str, list[str]]] = {}

        self._load_knowledge_bases()

        self.generation_module = GenerationIntegrationModule(
            model_name=self.llm_config.model_name,
            temperature=self.llm_config.temperature,
            max_tokens=self.llm_config.max_tokens,
            api_key=self.llm_config.api_key,  # type: ignore
            base_url=self.llm_config.base_url
        )

        self.metadata_filter_extractor = MetadataFilterExtractor(
            model_name=self.llm_config.model_name,
            max_tokens=self.llm_config.max_tokens,
            api_key=self.llm_config.api_key,  # type: ignore
            base_url=self.llm_config.base_url
        )

        if self.config.reranker.enabled:
            if self.config.reranker.type == "siliconflow":
                from app.rag.rerankers.siliconflow_reranker import SiliconFlowReranker
                self.reranker = SiliconFlowReranker(self.config.reranker)
                logger.info("SiliconFlow Reranker initialized.")
            else:
                logger.warning(f"Reranker type '{self.config.reranker.type}' not recognized. Reranking disabled.")

        # Initialize cache manager if enabled
        self.cache_manager: CacheManager | None = None
        if self.config.cache.enabled:
            embeddings = get_embedding_model(self.config)
            cache_vector_host = self.config.cache.vector_host or self.config.vector_store.host
            cache_vector_port = self.config.cache.vector_port or self.config.vector_store.port
            self.cache_manager = CacheManager(
                redis_host=self.config.cache.redis_host,
                redis_port=self.config.cache.redis_port,
                redis_db=self.config.cache.redis_db,
                redis_password=self.config.cache.redis_password,
                ttl=self.config.cache.ttl,
                similarity_threshold=self.config.cache.similarity_threshold,
                embeddings=embeddings,
                l2_enabled=self.config.cache.l2_enabled,
                vector_host=cache_vector_host,
                vector_port=cache_vector_port,
                vector_collection=self.config.cache.vector_collection,
                vector_user=self.config.cache.vector_user,
                vector_password=self.config.cache.vector_password,
                vector_secure=self.config.cache.vector_secure,
            )
            logger.info("Cache manager initialized.")
        else:
            logger.info("Caching is disabled.")

        self._query_planner = QueryPlanner(
            generation_module=self.generation_module,
            metadata_filter_extractor=self.metadata_filter_extractor,
            cache_manager=self.cache_manager,
        )
        self._retrieval_executor = RetrievalExecutor(
            retrieval_modules=self.retrieval_modules,
            cache_manager=self.cache_manager,
        )
        self._post_processor = DocumentPostProcessor(self.data_sources)
        self._context_builder = ContextBuilder()
        self._response_generator = ResponseGenerator(
            generation_module=self.generation_module,
        )

        self._initialized = True
        logger.info("RAGService initialized successfully with multiple knowledge bases.")

    def _load_knowledge_bases(self):
        """
        Loads data, creates embeddings, and sets up retrievers for all configured sources.
        """
        logger.info("Loading all knowledge bases...")
        embeddings = get_embedding_model(self.config)

        # Define the mapping from source name to class and config
        source_definitions = {
            "recipes": (HowToCookDataSource, self.config.data_source.howtocook),
            "tips": (TipsDataSource, self.config.data_source.tips),
        }

        for name, (source_class, source_config) in source_definitions.items():
            logger.info(f"--- Loading source: {name} ---")
            
            # 1. Instantiate Data Source
            data_path = Path(self.config.paths.base_data_path) / source_config.path_suffix
            
            init_params = {"data_path": str(data_path)}
            if hasattr(source_config, 'window_size'):
                init_params['window_size'] = source_config.window_size
            if hasattr(source_config, 'headers_to_split_on'):
                init_params['headers_to_split_on'] = source_config.headers_to_split_on

            data_source = source_class(**init_params)

            child_chunks = data_source.get_chunks()
            self.data_sources[name] = data_source
            self.metadata_catalog[name] = self._build_metadata_catalog(child_chunks)
            
            # Add a check to skip empty data sources
            if not child_chunks:
                logger.warning(f"Source '{name}' yielded no chunks. Skipping vector store and retrieval module setup.")
                continue

            # 2. Get Collection Name
            collection_name = self.config.vector_store.collection_names.get(name)
            if not collection_name:
                logger.error(f"Collection for source '{name}' not in config. Skipping.")
                continue

            # 3. Get Vector Store instance
            vector_store = get_vector_store(
                vs_config=self.config.vector_store,
                collection_name=collection_name,
                embeddings=embeddings,
                chunks=child_chunks,
                force_rebuild=False
            )
            
            # 4. Create and store Retrieval Module
            retrieval_module = RetrievalOptimizationModule(
                vectorstore=vector_store,
                child_chunks=child_chunks,
                score_threshold=self.config.retrieval.score_threshold,
                default_ranker_type=self.config.retrieval.ranker_type,
                default_ranker_weights=self.config.retrieval.ranker_weights
            )
            self.retrieval_modules[name] = retrieval_module
            logger.info(f"--- Source '{name}' loaded successfully. ---")

    # =========================================================================
    # Public API - Two main interfaces
    # =========================================================================

    def retrieve(
        self, 
        query: str, 
        use_intelligent_ranker: bool = True
    ) -> RetrievalResult:
        """
        Perform query rewriting and retrieval only, without LLM generation.
        
        This is designed for conversation service where:
        1. Query is rewritten for better retrieval
        2. Context is retrieved from knowledge base
        3. The caller (conversation service) handles LLM generation with full chat history
        
        Args:
            query: The search query (can be the rewritten query from conversation context)
            use_intelligent_ranker: Whether to use intelligent ranking
            
        Returns:
            RetrievalResult containing rewritten query, context and documents
        """
        if not self.retrieval_modules:
            raise RuntimeError("RAG Service is not properly initialized.")

        logger.info(f"Performing RAG retrieval for query: {query[:50]}...")

        # Query planning (rewrite + metadata extraction)
        plan = self._query_planner.prepare(query, self.metadata_catalog)
        
        # Execute retrieval
        all_retrieved_docs = self._retrieval_executor.retrieve(
            plan.rewritten_query,
            self.config.retrieval.top_k,
            use_intelligent_ranker,
            plan.metadata_expression,
        )

        # Rerank if enabled
        reranked_docs = self._rerank_if_needed(plan.rewritten_query, all_retrieved_docs)
        
        # Post-process documents
        processed_docs = self._post_processor.process(reranked_docs)
        
        # Build context string
        context_parts = self._context_builder.build(processed_docs)
        context = "\n\n".join(context_parts) if context_parts else ""
        
        # Extract sources for frontend display
        sources = self._extract_sources(processed_docs)
        
        logger.info(f"Retrieved {len(processed_docs)} documents for query")
        
        return RetrievalResult(
            original_query=query,
            rewritten_query=plan.rewritten_query,
            context=context,
            documents=processed_docs,
            sources=sources
        )

    def ask_with_generation(
        self, 
        query: str, 
        stream: bool = False, 
        use_intelligent_ranker: bool = True
    ) -> str | Generator[str, None, None]:
        """
        Full RAG pipeline: query rewriting + retrieval + LLM generation.
        
        This is used by the /chat endpoint for simple Q&A without conversation history.
        
        Args:
            query: The user's question
            stream: Whether to stream the response
            use_intelligent_ranker: Whether to use intelligent ranking
            
        Returns:
            Generated response string or generator for streaming
        """
        if not all([self.retrieval_modules, self.generation_module, self.data_sources]):
            raise RuntimeError("RAG Service is not properly initialized.")

        plan = self._query_planner.prepare(query, self.metadata_catalog)

        retrieval_top_k = self.config.retrieval.top_k
        all_retrieved_docs = self._retrieval_executor.retrieve(
            plan.rewritten_query,
            retrieval_top_k,
            use_intelligent_ranker,
            plan.metadata_expression,
        )

        reranked_docs = self._rerank_if_needed(plan.rewritten_query, all_retrieved_docs)
        processed_docs = self._post_processor.process(reranked_docs)
        context_parts = self._context_builder.build(processed_docs)
        result = self._response_generator.generate(plan.rewritten_query, context_parts, stream)
        
        # Convert Iterator to Generator if needed
        if isinstance(result, str):
            return result
        else:
            return (chunk for chunk in result)

    @staticmethod
    def _resolve_llm_config(
        base_llm: LLMProviderConfig, override: LLMOverrideConfig | None
    ) -> LLMProviderConfig:
        """Apply optional module-level overrides to the global LLM config."""
        if not override:
            return base_llm

        base_copy = base_llm.model_copy(deep=True)
        override_data = {k: v for k, v in override.model_dump().items() if v is not None}
        return base_copy.model_copy(update=override_data)

    # =========================================================================
    # Helper methods
    # =========================================================================

    def _rerank_if_needed(self, rewritten_query: str, docs_for_rerank):
        if self.reranker and self.config.reranker.enabled:
            logger.info(f"Reranking {len(docs_for_rerank)} documents...")
            return self.reranker.rerank(rewritten_query, docs_for_rerank)
        return docs_for_rerank

    def _build_metadata_catalog(self, chunks: list) -> Dict[str, list[str]]:
        catalog: Dict[str, set[str]] = {}
        for doc in chunks:
            meta = getattr(doc, "metadata", {}) or {}
            for k, v in meta.items():
                if k not in ["category", "dish_name", "difficulty"]:
                    continue
                if v is None:
                    continue
                if isinstance(v, (str, int, float)):
                    catalog.setdefault(k, set()).add(str(v))
        return {k: sorted(list(vals)) for k, vals in catalog.items()}

    def _extract_sources(self, documents: List[Document]) -> List[Dict]:
        """Extract source information from documents for frontend display."""
        sources = []
        seen = set()
        
        for doc in documents:
            metadata = doc.metadata or {}
            title = metadata.get("dish_name") or metadata.get("title") or metadata.get("source_title")
            info = title or metadata.get("category") or metadata.get("source", "CookHero 知识库")
            source_info: Dict[str, str] = {
                "type": metadata.get("source_type", "knowledge_base"),
                "info": info,
            }
            if title:
                source_info["title"] = title
            if metadata.get("url"):
                source_info["url"] = str(metadata["url"])
            if metadata.get("category"):
                source_info["category"] = metadata.get("category", "")
            
            # Deduplicate
            key = (source_info["type"], source_info["info"])
            if key not in seen:
                seen.add(key)
                sources.append(source_info)
        
        return sources[:5]  # Limit to top 5 sources


# Instantiate the singleton service
rag_service_instance = RAGService()
