# app/rag/rag_service.py
import logging
from typing import Dict, Any

from sklearn import base

from app.rag.config import DefaultRAGConfig
from app.rag.data_preparation import DataPreparationModule
from app.rag.index_construction import IndexConstructionModule
from app.rag.retrieval_optimization import RetrievalOptimizationModule
from app.rag.generation_integration import GenerationIntegrationModule

logger = logging.getLogger(__name__)

class RAGService:
    """
    Orchestrates the entire RAG pipeline.
    This is a singleton class to ensure that the expensive models and data
    are loaded only once.
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(RAGService, cls).__new__(cls)
        return cls._instance

    def __init__(self, config=None):
        # The __init__ will be called every time RAGService() is invoked,
        # but the expensive setup should only run once.
        if hasattr(self, '_initialized') and self._initialized:
            return
            
        logger.info("Initializing RAGService for the first time...")
        self.config = config or DefaultRAGConfig
        
        # Initialize all modules
        self.data_prep_module = DataPreparationModule(
            data_path=self.config.DATA_PATH,
            headers_to_split_on=self.config.HEADERS_TO_SPLIT_ON
        )
        self.index_module = IndexConstructionModule(
            config=self.config
        )
        self.retrieval_module = None # Depends on data and index
        self.generation_module = GenerationIntegrationModule(
            model_name=self.config.LLM_MODEL,
            temperature=self.config.TEMPERATURE,
            max_tokens=self.config.MAX_TOKENS,
            api_key=self.config.LLM_API_KEY,
            base_url=self.config.LLM_BASE_URL
        )
        
        self._load_knowledge_base()
        self._initialized = True
        logger.info("RAGService initialized successfully.")

    def _load_knowledge_base(self):
        """Loads data and builds/loads the index."""
        logger.info("Loading knowledge base...")
        # Load documents and create chunks
        self.data_prep_module.load_and_process_documents()
        
        # Build or load the vector index
        self.index_module.build_or_load_index(
            chunks=self.data_prep_module.child_chunks
        )
        
        # Now that the index is ready, initialize the retrieval module
        self.retrieval_module = RetrievalOptimizationModule(
            vectorstore=self.index_module.get_vectorstore(),
            child_chunks=self.data_prep_module.child_chunks
        )
        logger.info("Knowledge base loaded and retrievers are ready.")

    def ask(self, query: str, stream: bool = False):
        """
        Main method to ask a question to the RAG system.
        Args:
            query: The user's question.
            stream: Whether to stream the response.
        Returns:
            The generated answer or a streaming generator.
        """
        if not self.retrieval_module:
            raise RuntimeError("RAG Service is not properly initialized. Retrieval module is missing.")

        # 1. Route query
        route = self.generation_module.route_query(query)

        # 2. Rewrite query (optional, based on routing or other logic)
        rewritten_query = self.generation_module.rewrite_query(query)
        
        # 3. Retrieve documents
        # TODO: Add metadata filtering based on query analysis
        retrieved_docs = self.retrieval_module.hybrid_search(rewritten_query, top_k=self.config.TOP_K)
        
        # 4. Generate response
        response = self.generation_module.generate_response(
            query=rewritten_query,
            context_docs=retrieved_docs,
            stream=stream
        )
        
        return response

# Instantiate the singleton service
rag_service_instance = RAGService()
