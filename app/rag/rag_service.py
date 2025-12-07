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
from app.rag.rerankers.base import BaseReranker

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

        self._load_knowledge_bases()

        self.generation_module = GenerationIntegrationModule(
            model_name=self.config.llm.model_name,
            temperature=self.config.llm.temperature,
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

        # 1. Rewrite Query
        rewritten_query = self.generation_module.rewrite_query(query)
        
        # Detect if this is a recommendation query (needs more results)
        is_recommendation_query = self._is_recommendation_query(rewritten_query)
        # Increase top_k for recommendation queries to get more diverse results
        retrieval_top_k = self.config.retrieval.top_k * 2 if is_recommendation_query else self.config.retrieval.top_k
        if is_recommendation_query:
            logger.info(f"Detected recommendation query, increasing retrieval top_k to {retrieval_top_k}")

        # 2. Parallel Retrieval from all sources
        logger.info("--- Starting parallel retrieval from all data sources ---")
        all_retrieved_docs = []
        for name, retrieval_module in self.retrieval_modules.items():
            logger.info(f"Retrieving from source: {name}")
            
            # Determine ranker type for this specific retrieval
            ranker_type, ranker_weights = None, None
            if use_intelligent_ranker:
                 ranker_type, ranker_weights = retrieval_module.intelligent_ranker_selection(rewritten_query)

            # Retrieve docs from one source
            retrieved_docs, retrieved_scores = retrieval_module.hybrid_search(
                rewritten_query,
                top_k=retrieval_top_k, # Use adjusted top_k for recommendation queries
                ranker_type=ranker_type,
                ranker_weights=ranker_weights
            )
            # Add source name and score to metadata for later processing
            for doc, score in zip(retrieved_docs, retrieved_scores):
                doc.metadata['data_source'] = name
                doc.metadata['retrieval_score'] = score
            all_retrieved_docs.extend(retrieved_docs)
        
        logger.info(f"--- Aggregated {len(all_retrieved_docs)} documents from all sources ---")

        # 3. Unified Post-processing and Reranking
        
        # First, apply source-specific post-processing
        processed_docs = []
        # Separate docs by source
        docs_by_source = {}
        for doc in all_retrieved_docs:
            source_name = doc.metadata.get('data_source')
            if source_name not in docs_by_source:
                docs_by_source[source_name] = []
            docs_by_source[source_name].append(doc)

        for source_name, docs in docs_by_source.items():
            data_source = self.data_sources[source_name]
            # generic_text chunks are processed as is, others get parent documents
            processed_docs.extend(data_source.post_process_retrieval(docs))

        # Remove duplicates that might arise from post-processing
        # Use a dict to track unique docs and keep the one with highest score
        unique_processed_docs_dict = {}
        for doc in processed_docs:
            content_key = doc.page_content
            current_score = doc.metadata.get('retrieval_score', 0.0)
            if content_key not in unique_processed_docs_dict:
                unique_processed_docs_dict[content_key] = doc
            else:
                # Keep the doc with higher score
                existing_score = unique_processed_docs_dict[content_key].metadata.get('retrieval_score', 0.0)
                if current_score > existing_score:
                    unique_processed_docs_dict[content_key] = doc
        
        unique_processed_docs = list(unique_processed_docs_dict.values())
        logger.info(f"Total unique documents after post-processing: {len(unique_processed_docs)}")
        
        # Sort documents by retrieval score (highest first) and take top_k before reranking
        unique_processed_docs.sort(
            key=lambda doc: doc.metadata.get('retrieval_score', 0.0),
            reverse=True
        )
        
        # Use retrieval.top_k as the limit before reranking
        # For recommendation queries, allow more documents to pass through
        top_k_before_rerank = retrieval_top_k if is_recommendation_query else self.config.retrieval.top_k
        docs_for_rerank = unique_processed_docs[:top_k_before_rerank]
        if docs_for_rerank:
            logger.info(f"Selected top {len(docs_for_rerank)} documents (score range: "
                       f"{docs_for_rerank[-1].metadata.get('retrieval_score', 0.0):.4f} - "
                       f"{docs_for_rerank[0].metadata.get('retrieval_score', 0.0):.4f}) for reranking")
        else:
            logger.warning("No documents selected for reranking after post-processing and sorting.")
        
        # Now, rerank the top-k documents
        if self.reranker and self.config.reranker.enabled:
            logger.info(f"Reranking {len(docs_for_rerank)} documents...")
            final_docs = self.reranker.rerank(rewritten_query, docs_for_rerank)
        else:
            final_docs = docs_for_rerank

        # 4. Build final context for LLM
        context_parts = []
        for doc in final_docs:
            source_name = doc.metadata.get('data_source')
            # If the doc is a sentence chunk, use its window context
            if source_name == 'generic_text' and 'window' in doc.metadata:
                context_parts.append(doc.metadata['window'])
            else:
                context_parts.append(doc.page_content)
        
        # 5. Generate Response
        response = self.generation_module.generate_response(
            query=rewritten_query,
            context_docs=context_parts,
            stream=stream
        )

        return response

# Instantiate the singleton service
rag_service_instance = RAGService()
