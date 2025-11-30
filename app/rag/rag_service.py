# app/rag/rag_service.py
import logging

from app.core.config_loader import DefaultRAGConfig
from app.core.rag_config import RAGConfig
from app.rag.data_sources.howtocook_data_source import HowToCookDataSource
from app.rag.embeddings.embedding_factory import get_embedding_model
from app.rag.vector_stores.vector_store_factory import get_vector_store
from app.rag.retrieval_optimization import RetrievalOptimizationModule
from app.rag.generation_integration import GenerationIntegrationModule

logger = logging.getLogger(__name__)

class RAGService:
    """
    Orchestrates the entire RAG pipeline using a modular, factory-based architecture.
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
        
        self.generation_module = GenerationIntegrationModule(
            model_name=self.config.llm.model_name,
            temperature=self.config.llm.temperature,
            max_tokens=self.config.llm.max_tokens,
            api_key=self.config.llm.api_key, # type: ignore
            base_url=self.config.llm.base_url
        )
        
        self._initialized = True
        logger.info("RAGService initialized successfully.")

    def _load_knowledge_base(self, force_rebuild=False):
        """
        Loads data, creates embeddings, builds the vector store, and sets up retrievers.
        """
        logger.info("Loading knowledge base...")
        
        # 1. Data Source gets instantiated and loads/processes data internally
        self.data_source = HowToCookDataSource(
            data_path=self.config.paths.data_path,
            headers_to_split_on=self.config.data_source.howtocook.headers_to_split_on
        )
        child_chunks = self.data_source.get_chunks()
        
        # 2. Embedding Model
        embeddings = get_embedding_model(self.config)
        
        # 3. Vector Store
        vector_store = get_vector_store(
            config=self.config,
            embeddings=embeddings,
            chunks=child_chunks,
            force_rebuild=force_rebuild
        )
        
        # 4. Retrieval Module with configuration
        self.retrieval_module = RetrievalOptimizationModule(
            vectorstore=vector_store,
            child_chunks=child_chunks,
            score_threshold=self.config.retrieval.score_threshold,
            default_ranker_type=self.config.retrieval.ranker_type,
            default_ranker_weights=self.config.retrieval.ranker_weights
        )
        logger.info("Knowledge base loaded and retrievers are ready.")

    def ask(self, query: str, stream: bool = False, use_intelligent_ranker: bool = True):
        """
        Main method to ask a question to the RAG system.
        
        Args:
            query: User's question.
            stream: Whether to stream the response.
            use_intelligent_ranker: Whether to use intelligent ranker selection based on query.
        """
        if not all([self.retrieval_module, self.generation_module, self.data_source]):
            raise RuntimeError("RAG Service is not properly initialized.")

        # 1. Route and Rewrite Query
        rewritten_query = self.generation_module.rewrite_query(query)
        
        # 2. Determine ranker type and weights based on query
        ranker_type = None
        ranker_weights = None
        if use_intelligent_ranker:
            ranker_type, ranker_weights = self.retrieval_module.intelligent_ranker_selection(rewritten_query)
        
        # 3. Retrieve small chunks with scores
        retrieved_chunks, scores = self.retrieval_module.hybrid_search(
            rewritten_query, 
            top_k=self.config.retrieval.top_k,
            ranker_type=ranker_type,
            ranker_weights=ranker_weights
        )
        
        # 4. Post-process retrieval to get large documents
        final_docs = self.data_source.post_process_retrieval(retrieved_chunks)
        
        # 5. Generate response using the large documents
        response = self.generation_module.generate_response(
            query=rewritten_query,
            context_docs=final_docs,
            stream=stream
        )
        
        return response

# Instantiate the singleton service
rag_service_instance = RAGService()
