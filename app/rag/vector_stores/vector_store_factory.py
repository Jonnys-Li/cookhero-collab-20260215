# app/rag/vector_stores/vector_store_factory.py
import logging
from typing import List, Dict, Any
from pymilvus import utility, connections, DataType
from langchain_milvus import Milvus, BM25BuiltInFunction
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from app.core.rag_config import VectorStoreConfig

logger = logging.getLogger(__name__)

# Define metadata fields that should be indexed as scalar fields for filtering
# These fields will be searchable via Milvus expressions
# Format: {field_name: {"dtype": DataType, "max_length": int (for VARCHAR)}}
METADATA_SCALAR_SCHEMA: Dict[str, Any] = {
    "category": {"dtype": DataType.VARCHAR, "max_length": 128},
    "difficulty": {"dtype": DataType.VARCHAR, "max_length": 64},
    "dish_name": {"dtype": DataType.VARCHAR, "max_length": 256},
}

def get_vector_store(
    vs_config: VectorStoreConfig,
    collection_name: str,
    embeddings: Embeddings,
    chunks: List[Document],
    force_rebuild: bool = False
) -> Milvus:
    """
    Factory function to get a Milvus vector store instance.
    Connects to the Milvus collection, creating it if it doesn't exist.
    
    Args:
        vs_config: The vector store configuration object.
        collection_name: The specific name of the collection to connect to or create.
        embeddings: The embedding model instance to use.
        chunks: A list of Document chunks to be indexed if the collection is new.
        force_rebuild: If True, drops the existing collection and rebuilds it.
        
    Returns:
        An instance of the Milvus vector store.
    """
    connection_args = {"host": vs_config.host, "port": vs_config.port}
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

        # Use BM25BuiltInFunction for hybrid search (dense + sparse vectors)
        logger.info("Initializing Milvus with BM25 built-in function for hybrid search")
        logger.info(f"Adding metadata scalar fields for filtering: {list(METADATA_SCALAR_SCHEMA.keys())}")
        
        vector_store = Milvus.from_documents(
            documents=chunks,
            embedding=embeddings,
            collection_name=collection_name,
            connection_args=connection_args,
            text_field="text",
            vector_field=["dense", "sparse"],  # dense for embeddings, sparse for BM25
            builtin_function=BM25BuiltInFunction(),
            metadata_schema=METADATA_SCALAR_SCHEMA,  # Add scalar fields for filtering
        )
        logger.info(f"Successfully created and populated Milvus collection: {collection_name}")
    else:
        logger.info(f"Connecting to existing Milvus collection: {collection_name}")
        vector_store = Milvus(
            embedding_function=embeddings,
            collection_name=collection_name,
            connection_args=connection_args,
            text_field="text",
            vector_field=["dense", "sparse"],
            builtin_function=BM25BuiltInFunction(),
            metadata_schema=METADATA_SCALAR_SCHEMA,  # Include schema for existing collection
        )
        logger.info(f"Successfully connected to Milvus collection: {collection_name}")
        
    return vector_store
