# app/rag/rag_service.py
import logging
from pathlib import Path
from typing import Dict

from app.core.config_loader import DefaultRAGConfig
from app.core.rag_config import RAGConfig
from app.rag.data_sources.base import BaseDataSource
from app.rag.data_sources.howtocook_data_source import HowToCookDataSource
from app.rag.data_sources.tips_data_source import TipsDataSource
from app.rag.data_sources.generic_text_data_source import GenericTextDataSource
from app.rag.embeddings.embedding_factory import get_embedding_model
from app.rag.vector_stores.vector_store_factory import get_vector_store
from app.rag.pipeline.retrieval import RetrievalOptimizationModule
from app.rag.pipeline.generation import GenerationIntegrationModule
from app.rag.pipeline.metadata_filter import MetadataFilterExtractor
from app.rag.rerankers.base import BaseReranker
from app.rag.cache import CacheManager

logger = logging.getLogger(__name__)


class RAGService:
    """
    Orchestrates the entire RAG pipeline, supporting multiple data sources
    and query routing.
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
        
        self.data_sources: Dict[str, BaseDataSource] = {}
        self.retrieval_modules: Dict[str, RetrievalOptimizationModule] = {}
        self.reranker: BaseReranker | None = None
        self.metadata_catalog: Dict[str, Dict[str, list[str]]] = {}

        self._load_knowledge_bases()

        self.generation_module = GenerationIntegrationModule(
            model_name=self.config.llm.model_name,
            temperature=self.config.llm.temperature,
            max_tokens=self.config.llm.max_tokens,
            api_key=self.config.llm.api_key,  # type: ignore
            base_url=self.config.llm.base_url
        )

        self.metadata_filter_extractor = MetadataFilterExtractor(
            model_name=self.config.llm.model_name,
            max_tokens=self.config.llm.max_tokens,
            api_key=self.config.llm.api_key,  # type: ignore
            base_url=self.config.llm.base_url
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
            self.cache_manager = CacheManager(
                redis_host=self.config.cache.redis_host,
                redis_port=self.config.cache.redis_port,
                redis_db=self.config.cache.redis_db,
                redis_password=self.config.cache.redis_password,
                retrieval_ttl=self.config.cache.retrieval_ttl,
                response_ttl=self.config.cache.response_ttl,
                similarity_threshold=self.config.cache.similarity_threshold,
                embeddings=embeddings,
                l2_enabled=self.config.cache.l2_enabled
            )
            logger.info("Cache manager initialized.")
        else:
            logger.info("Caching is disabled.")

        self._initialized = True
        logger.info("RAGService initialized successfully with multiple knowledge bases.")
    
    def _is_recommendation_query(self, query: str) -> bool:
        """
        Detects if a query is a recommendation query that needs more diverse results.
        
        Args:
            query: The rewritten query string.
            
        Returns:
            True if this is a recommendation query, False otherwise.
        """
        query_lower = query.lower()
        recommendation_keywords = [
            "推荐", "有哪些", "有什么", "适合", "建议", "搭配", "组合",
            "recommend", "what", "which", "suggest", "suitable"
        ]
        return any(keyword in query_lower for keyword in recommendation_keywords)

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
            "generic_text": (GenericTextDataSource, self.config.data_source.generic_text),
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

    def ask(self, query: str, stream: bool = False, use_intelligent_ranker: bool = True):
        """
        Main method to ask a question. It fetches from all data sources in parallel,
        then reranks the aggregated results to generate a response.
        """
        if not all([self.retrieval_modules, self.generation_module, self.data_sources]):
            raise RuntimeError("RAG Service is not properly initialized.")

        rewritten_query = self._rewrite_query(query)
        metadata_filters = self.metadata_filter_extractor.extract_filters(
            query,
            self._merge_metadata_catalog()
        )
        cached = self._maybe_return_cached_response(rewritten_query)
        if cached is not None:
            return cached

        retrieval_top_k = self.config.retrieval.top_k
        all_retrieved_docs = self._retrieve_from_all_sources(
            rewritten_query,
            retrieval_top_k,
            use_intelligent_ranker,
            metadata_filters,
        )

        processed_docs = self._post_process(all_retrieved_docs)
        docs_for_rerank = self._select_for_rerank(processed_docs, retrieval_top_k)
        final_docs = self._rerank_if_needed(rewritten_query, docs_for_rerank)
        context_parts = self._build_context(final_docs)
        return self._generate_and_cache_response(rewritten_query, context_parts, stream)

    # --- Helper methods ---

    def _rewrite_query(self, query: str) -> str:
        return self.generation_module.rewrite_query(query)

    def _maybe_return_cached_response(self, rewritten_query: str):
        if not self.cache_manager:
            return None
        cached_response = self.cache_manager.get_response_cache(rewritten_query)
        if cached_response:
            logger.info("Returning cached response")
            return cached_response
        return None

    def _retrieve_from_all_sources(
        self,
        rewritten_query: str,
        retrieval_top_k: int,
        use_intelligent_ranker: bool,
        metadata_filters: list,
    ):
        logger.info("--- Starting parallel retrieval from all data sources ---")
        all_retrieved_docs = []
        expr = self._build_milvus_expr(
            metadata_filters
        )
        for name, retrieval_module in self.retrieval_modules.items():
            logger.info(f"Retrieving from source: {name}")
            # Filter metadata_filters to only include keys that exist in this source's catalog
            # If metadata filters exist, bypass cached retrieval (cache key未区分过滤条件)
            cached_docs = None if metadata_filters else (self.cache_manager.get_retrieval_cache(name, rewritten_query) if self.cache_manager else None)

            if cached_docs:
                logger.info(f"Using cached retrieval results for source '{name}': {len(cached_docs)} documents")
                for doc in cached_docs:
                    if 'retrieval_score' not in doc.metadata:
                        doc.metadata['retrieval_score'] = 1.0
                    doc.metadata['data_source'] = name
                all_retrieved_docs.extend(cached_docs)
                continue

            ranker_type = ranker_weights = None
            if use_intelligent_ranker:
                ranker_type, ranker_weights = retrieval_module.intelligent_ranker_selection(rewritten_query)

            try:
                retrieved_docs, retrieved_scores = retrieval_module.hybrid_search(
                    rewritten_query,
                    top_k=retrieval_top_k,
                    ranker_type=ranker_type,
                    ranker_weights=ranker_weights,
                    expr=expr,
                )
            except Exception as e:
                logger.error(f"Error during retrieval from source '{name}': {e}")
                continue
            
            for doc, score in zip(retrieved_docs, retrieved_scores):
                doc.metadata['data_source'] = name
                doc.metadata['retrieval_score'] = score
            all_retrieved_docs.extend(retrieved_docs)

            if self.cache_manager:
                self.cache_manager.set_retrieval_cache(name, rewritten_query, retrieved_docs)

        logger.info(f"--- Aggregated {len(all_retrieved_docs)} documents from all sources ---")
        return all_retrieved_docs

    def _post_process(self, all_retrieved_docs):
        processed_docs = []
        docs_by_source = {}
        for doc in all_retrieved_docs:
            source_name = doc.metadata.get('data_source')
            docs_by_source.setdefault(source_name, []).append(doc)

        for source_name, docs in docs_by_source.items():
            data_source = self.data_sources[source_name]
            processed_docs.extend(data_source.post_process_retrieval(docs))

        unique_processed_docs_dict = {}
        for doc in processed_docs:
            content_key = doc.page_content
            current_score = doc.metadata.get('retrieval_score', 0.0)
            if content_key not in unique_processed_docs_dict:
                unique_processed_docs_dict[content_key] = doc
            else:
                existing_score = unique_processed_docs_dict[content_key].metadata.get('retrieval_score', 0.0)
                if current_score > existing_score:
                    unique_processed_docs_dict[content_key] = doc

        unique_processed_docs = list(unique_processed_docs_dict.values())
        logger.info(f"Total unique documents after post-processing: {len(unique_processed_docs)}")
        unique_processed_docs.sort(
            key=lambda doc: doc.metadata.get('retrieval_score', 0.0),
            reverse=True,
        )
        return unique_processed_docs

    def _select_for_rerank(self, processed_docs, retrieval_top_k: int):
        top_k_before_rerank = retrieval_top_k
        docs_for_rerank = processed_docs[:top_k_before_rerank]
        if docs_for_rerank:
            logger.info(
                f"Selected top {len(docs_for_rerank)} documents (score range: "
                f"{docs_for_rerank[-1].metadata.get('retrieval_score', 0.0):.4f} - "
                f"{docs_for_rerank[0].metadata.get('retrieval_score', 0.0):.4f}) for reranking"
            )
        else:
            logger.warning("No documents selected for reranking after post-processing and sorting.")
        return docs_for_rerank

    def _rerank_if_needed(self, rewritten_query: str, docs_for_rerank):
        if self.reranker and self.config.reranker.enabled:
            logger.info(f"Reranking {len(docs_for_rerank)} documents...")
            return self.reranker.rerank(rewritten_query, docs_for_rerank)
        return docs_for_rerank

    def _build_context(self, final_docs):
        context_parts = []
        for doc in final_docs:
            source_name = doc.metadata.get('data_source')
            if source_name == 'generic_text' and 'window' in doc.metadata:
                context_parts.append(doc.metadata['window'])
            else:
                context_parts.append(doc.page_content)
        return context_parts

    def _generate_and_cache_response(self, rewritten_query: str, context_parts, stream: bool):
        response = self.generation_module.generate_response(
            query=rewritten_query,
            context_docs=context_parts,
            stream=stream,
        )
        if not stream and self.cache_manager is not None and isinstance(response, str):
            self.cache_manager.set_response_cache(rewritten_query, response)
        return response

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
        res =  {k: sorted(list(vals)) for k, vals in catalog.items()}
        return res

    def _merge_metadata_catalog(self) -> Dict[str, list[str]]:
        merged: Dict[str, set[str]] = {}
        for source_catalog in self.metadata_catalog.values():
            for k, vals in source_catalog.items():
                merged.setdefault(k, set()).update(vals)
        res = {k: sorted(list(vals)) for k, vals in merged.items()}
        return res

    def _build_milvus_expr(self, filters: list) -> str | None:
        """
        Build Milvus boolean expression from filters.
        Example: category in ["素菜","荤菜"] and difficulty in ["简单"]
        
        Note: In Milvus, metadata fields are accessed directly by their field name,
        not through a "metadata" prefix. The fields should be indexed as scalar fields.
        """
        if not filters:           
            return None
        clauses = []
        for f in filters:
            key = f.get("key")
            values = f.get("values", [])
            if not key or not values:
                continue
            # Escape quotes in values and wrap them
            safe_vals = [f'"{str(v).replace(chr(34), chr(92)+chr(34))}"' for v in values]
            if not safe_vals:
                continue
            # Direct field name access (not metadata["field"])
            clause = f'{key} in [{", ".join(safe_vals)}]'
            clauses.append(clause)
        if not clauses:
            return None
        res = " and ".join(clauses)
        logger.info(f"{'*' * 10} Built Milvus expression: {res}")
        return res

# Instantiate the singleton service
rag_service_instance = RAGService()
