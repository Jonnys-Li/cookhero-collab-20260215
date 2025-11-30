# app/rag/embeddings/embedding_factory.py
import logging
from langchain_core.embeddings import Embeddings
from app.rag.config import RAGConfig

logger = logging.getLogger(__name__)

def get_embedding_model(config: RAGConfig) -> Embeddings:
    """
    Factory function to create and return an embedding model based on the config.
    
    Args:
        config: The RAG configuration object.
        
    Returns:
        An instance of an embedding model.
    """
    mode = config.embedding.mode
    logger.info(f"Creating embedding model in '{mode}' mode.")

    if mode == 'local':
        from langchain_huggingface import HuggingFaceEmbeddings
        logger.info(f"Initializing local embedding model: {config.embedding.local_model}")
        return HuggingFaceEmbeddings(
            model_name=config.embedding.local_model,
            model_kwargs={'device': 'cpu'},
            encode_kwargs={'normalize_embeddings': True}
        )
    elif mode == 'remote':
        from langchain_openai import OpenAIEmbeddings
        logger.info(f"Initializing remote embedding model: {config.embedding.remote_model}")
        if not config.embedding.api_key:
            raise ValueError("EMBEDDING_API_KEY must be set in .env for remote embedding mode.")
        
        return OpenAIEmbeddings(
            model=config.embedding.remote_model,
            api_key=config.embedding.api_key, # type: ignore
            base_url=config.embedding.api_url,
            chunk_size=config.embedding.batch_size,
        )
    else:
        raise ValueError(f"Invalid EMBEDDING_MODE: {mode}")
