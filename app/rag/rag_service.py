# app/rag/rag_service.py
import logging

from app.rag.config import DefaultRAGConfig, RAGConfig
from app.rag.data_sources.howtocook_data_source import HowToCookDataSource
from app.rag.data_preparation import DataPreparationModule
from app.rag.embeddings.embedding_factory import get_embedding_model
from app.rag.vector_stores.vector_store_factory import get_vector_store
from app.rag.retrieval_optimization import RetrievalOptimizationModule
from app.rag.generation_integration import GenerationIntegrationModule

logger = logging.getLogger(__name__)

class RAGService:
    """
    Orchestrates the entire RAG pipeline using a modular, factory-based architecture.
    This is a singleton class to ensure models and data are loaded only once.
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
        
        self._load_knowledge_base(force_rebuild=True)
        
        # Initialize the generation module
        self.generation_module = GenerationIntegrationModule(
            model_name=self.config.LLM_MODEL,
            temperature=self.config.TEMPERATURE,
            max_tokens=self.config.MAX_TOKENS,
            api_key=self.config.LLM_API_KEY,
            base_url=self.config.LLM_BASE_URL
        )
        
        self._initialized = True
        logger.info("RAGService initialized successfully.")

    def _load_knowledge_base(self, force_rebuild=False):
        """
        Loads data, creates embeddings, builds the vector store, and sets up retrievers.
        """
        logger.info("Loading knowledge base...")
        
        # 1. Data Source and Preparation
        data_source = HowToCookDataSource(data_path=self.config.DATA_PATH)
        data_prep_module = DataPreparationModule(
            data_source=data_source,
            headers_to_split_on=self.config.HEADERS_TO_SPLIT_ON
        )
        data_prep_module.run()
        
        # 2. Embedding Model
        embeddings = get_embedding_model(self.config)
        
        # 3. Vector Store
        vector_store = get_vector_store(
            config=self.config,
            embeddings=embeddings,
            chunks=data_prep_module.child_chunks,
            force_rebuild=force_rebuild
        )
        
        # 4. Retrieval Module
        self.retrieval_module = RetrievalOptimizationModule(
            vectorstore=vector_store,
            child_chunks=data_prep_module.child_chunks
        )
        logger.info("Knowledge base loaded and retrievers are ready.")

    def ask(self, query: str, stream: bool = False):
        """
        Main method to ask a question to the RAG system.
        """
        if not self.retrieval_module or not self.generation_module:
            raise RuntimeError("RAG Service is not properly initialized.")

        # 1. Route query
        route = self.generation_module.route_query(query)

        # 2. Rewrite query
        rewritten_query = self.generation_module.rewrite_query(query)
        
        # 3. Retrieve documents
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
