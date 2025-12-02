# app/rag/rag_service.py
import logging
from pathlib import Path
from typing import Dict

from app.core.config_loader import DefaultRAGConfig
from app.core.rag_config import RAGConfig
from app.rag.data_sources.base import BaseDataSource
from app.rag.data_sources.howtocook_data_source import HowToCookDataSource
from app.rag.data_sources.tips_data_source import TipsDataSource
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
            "tips": (TipsDataSource, self.config.data_source.tips)
        }

        for name, (source_class, source_config) in source_definitions.items():
            logger.info(f"--- Loading source: {name} ---")
            
            # 1. Instantiate Data Source
            data_path = Path(self.config.paths.base_data_path) / source_config.path_suffix
            data_source = source_class(
                data_path=str(data_path),
                headers_to_split_on=source_config.headers_to_split_on
            )
            child_chunks = data_source.get_chunks()
            self.data_sources[name] = data_source
            
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
        Main method to ask a question. It routes, retrieves, and generates a response.
        """
        if not all([self.retrieval_modules, self.generation_module, self.data_sources]):
            raise RuntimeError("RAG Service is not properly initialized.")

        # 1. Route Query to the correct data source
        route = self.generation_module.route_query(query)
        logger.info(f"Query routed to: {route}")

        retrieval_module = self.retrieval_modules.get(route)
        data_source = self.data_sources.get(route)

        if not retrieval_module or not data_source:
            raise RuntimeError(f"No retriever or data source found for route '{route}'")

        # 2. Rewrite Query
        rewritten_query = self.generation_module.rewrite_query(query)

        # 3. Determine ranker type and weights
        ranker_type, ranker_weights = None, None
        if use_intelligent_ranker:
            ranker_type, ranker_weights = retrieval_module.intelligent_ranker_selection(rewritten_query)

        # 4. Retrieve small chunks with scores from the selected retriever
        retrieved_chunks, _ = retrieval_module.hybrid_search(
            rewritten_query,
            top_k=self.config.retrieval.top_k,
            ranker_type=ranker_type,
            ranker_weights=ranker_weights
        )

        # 5. Post-process retrieval using the selected data source
        final_docs = data_source.post_process_retrieval(retrieved_chunks)

        # 6. Rerank final documents if enabled
        if self.reranker and self.config.reranker.enabled:
            final_docs = self.reranker.rerank(rewritten_query, final_docs)
        
        # 7. Generate response
        response = self.generation_module.generate_response(
            query=rewritten_query,
            context_docs=final_docs,
            stream=stream
        )

        return response

# Instantiate the singleton service
rag_service_instance = RAGService()
