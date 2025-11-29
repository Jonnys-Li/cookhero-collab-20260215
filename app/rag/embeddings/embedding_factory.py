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
    mode = config.EMBEDDING_MODE
    logger.info(f"Creating embedding model in '{mode}' mode.")

    if mode == 'local':
        from langchain_huggingface import HuggingFaceEmbeddings
        logger.info(f"Initializing local embedding model: {config.LOCAL_EMBEDDING_MODEL}")
        return HuggingFaceEmbeddings(
            model_name=config.LOCAL_EMBEDDING_MODEL,
            model_kwargs={'device': 'cpu'},
            encode_kwargs={'normalize_embeddings': True}
        )
    elif mode == 'remote':
        from langchain_openai import OpenAIEmbeddings
        logger.info(f"Initializing remote embedding model: {config.REMOTE_EMBEDDING_MODEL}")
        if not config.EMBEDDING_API_KEY or config.EMBEDDING_API_KEY == "None":
            raise ValueError("EMBEDDING_API_KEY must be set in config for remote embedding mode.")
        
        return OpenAIEmbeddings(
            model=config.REMOTE_EMBEDDING_MODEL,
            api_key=config.EMBEDDING_API_KEY, # type: ignore
            base_url=config.EMBEDDING_API_URL,
            chunk_size=config.EMBEDDING_BATCH_SIZE,
        )
    else:
        raise ValueError(f"Invalid EMBEDDING_MODE: {mode}")
