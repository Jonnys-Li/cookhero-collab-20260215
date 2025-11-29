# app/rag/vector_stores/vector_store_factory.py
import logging
from typing import List
from pymilvus import utility, connections
from langchain_milvus import Milvus
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from app.rag.config import RAGConfig

logger = logging.getLogger(__name__)

def get_vector_store(
    config: RAGConfig,
    embeddings: Embeddings,
    chunks: List[Document],
    force_rebuild: bool = False
) -> Milvus:
    """
    Factory function to get a Milvus vector store instance.
    Connects to the Milvus collection, creating it if it doesn't exist.
    
    Args:
        config: The RAG configuration object.
        embeddings: The embedding model instance to use.
        chunks: A list of Document chunks to be indexed if the collection is new.
        force_rebuild: If True, drops the existing collection and rebuilds it.
        
    Returns:
        An instance of the Milvus vector store.
    """
    collection_name = config.MILVUS_COLLECTION_NAME
    connection_args = {"host": config.MILVUS_HOST, "port": config.MILVUS_PORT}
    alias = "default"

    logger.info(f"Managing Milvus connection at {connection_args['host']}:{connection_args['port']}")
    
    try:
        connections.connect(alias=alias, **connection_args)
        if force_rebuild and utility.has_collection(collection_name, using=alias):
            logger.warning(f"Dropping existing Milvus collection: {collection_name}")
            _ = utility.drop_collection(collection_name, using=alias)
        
        collection_exists = utility.has_collection(collection_name, using=alias)
    finally:
        if connections.has_connection(alias):
            connections.disconnect(alias)
            logger.info(f"Disconnected from Milvus alias '{alias}' used for pre-flight checks.")

    if not collection_exists:
        logger.info(f"Milvus collection '{collection_name}' not found. Creating via LangChain...")
        if not chunks:
            raise ValueError("Cannot build a new collection from an empty list of chunks.")

        vector_store = Milvus.from_documents(
            documents=chunks,
            embedding=embeddings,
            collection_name=collection_name,
            connection_args=connection_args,
            text_field="text",
            vector_field="embedding",
        )
        logger.info(f"Successfully created and populated Milvus collection: {collection_name}")
    else:
        logger.info(f"Connecting to existing Milvus collection: {collection_name}")
        vector_store = Milvus(
            embedding_function=embeddings,
            collection_name=collection_name,
            connection_args=connection_args,
            text_field="text",
            vector_field="embedding",
        )
        logger.info(f"Successfully connected to Milvus collection: {collection_name}")
        
    return vector_store
