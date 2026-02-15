# app/rag/vector_stores/vector_store_factory.py
import logging
from typing import List, Dict, Any
from pymilvus import utility, connections, DataType
from langchain_milvus import Milvus, BM25BuiltInFunction
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from app.config.database_config import MilvusConfig

logger = logging.getLogger(__name__)

# Define metadata fields that should be indexed as scalar fields for filtering
# These fields will be searchable via Milvus expressions
# Format: {field_name: {"dtype": DataType, "max_length": int (for VARCHAR)}}
METADATA_SCALAR_SCHEMA: Dict[str, Any] = {
    "category": {"dtype": DataType.VARCHAR, "max_length": 128},
    "difficulty": {"dtype": DataType.VARCHAR, "max_length": 64},
    "dish_name": {"dtype": DataType.VARCHAR, "max_length": 256},
    "user_id": {"dtype": DataType.VARCHAR, "max_length": 64},
    "parent_id": {"dtype": DataType.VARCHAR, "max_length": 64},
    "source": {"dtype": DataType.VARCHAR, "max_length": 256},
    "data_source": {"dtype": DataType.VARCHAR, "max_length": 64},
    "source_type": {"dtype": DataType.VARCHAR, "max_length": 64},
    "is_dish_index": {"dtype": DataType.BOOL},
}


def _is_local_milvus_lite(host: str) -> bool:
    """Treat path-like hosts as Milvus Lite URIs."""
    return host.endswith(".db") or host.startswith("/") or host.startswith("./")


def _build_vector_store_kwargs(
    collection_name: str,
    connection_args: Dict[str, Any],
    use_hybrid_search: bool,
) -> Dict[str, Any]:
    """Build kwargs for langchain_milvus.Milvus constructor/factory."""
    kwargs: Dict[str, Any] = {
        "collection_name": collection_name,
        "connection_args": connection_args,
        "text_field": "text",
        "metadata_schema": METADATA_SCALAR_SCHEMA,
    }
    if use_hybrid_search:
        kwargs["vector_field"] = ["dense", "sparse"]
        kwargs["builtin_function"] = BM25BuiltInFunction()
    else:
        kwargs["index_params"] = {"metric_type": "L2", "index_type": "FLAT"}
    return kwargs


def get_vector_store(
    milvus_config: MilvusConfig,
    collection_name: str,
    embeddings: Embeddings,
    chunks: List[Document],
    force_rebuild: bool = False
) -> Milvus:
    """
    Factory function to get a Milvus vector store instance.
    Connects to the Milvus collection, creating it if it doesn't exist.
    
    Args:
        vs_config: The vector store configuration object (collection names, type).
        milvus_config: The Milvus connection configuration (host, port, credentials).
        collection_name: The specific name of the collection to connect to or create.
        embeddings: The embedding model instance to use.
        chunks: A list of Document chunks to be indexed if the collection is new.
        force_rebuild: If True, drops the existing collection and rebuilds it.
        
    Returns:
        An instance of the Milvus vector store.
    """
    use_hybrid_search = not _is_local_milvus_lite(milvus_config.host)
    if not use_hybrid_search:
        connection_args = {"uri": milvus_config.host}
    else:
        connection_args = {"host": milvus_config.host, "port": milvus_config.port}
    if milvus_config.user:
        connection_args["user"] = milvus_config.user
    if milvus_config.password:
        connection_args["password"] = milvus_config.password
    if milvus_config.secure:
        connection_args["secure"] = milvus_config.secure
    alias = "default"

    logger.info(f"Managing Milvus connection: {connection_args}")
    logger.info(
        "Milvus retrieval mode: %s",
        "hybrid(dense+sparse)" if use_hybrid_search else "dense-only",
    )
    
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

        # Enable hybrid mode when connected to full Milvus.
        # Milvus Lite (uri mode) runs in dense-only mode.
        logger.info(
            "Initializing Milvus collection (hybrid=%s)",
            use_hybrid_search,
        )
        logger.info(f"Adding metadata scalar fields for filtering: {list(METADATA_SCALAR_SCHEMA.keys())}")
        vector_store_kwargs = _build_vector_store_kwargs(
            collection_name=collection_name,
            connection_args=connection_args,
            use_hybrid_search=use_hybrid_search,
        )
        
        if chunks:
            # Normal path: create collection with documents
            vector_store = Milvus.from_documents(
                documents=chunks,
                embedding=embeddings,
                **vector_store_kwargs,
            )
        else:
            # Empty chunks: create collection with a placeholder document to ensure schema is created,
            # then delete the placeholder. This ensures metadata_schema fields are properly created.
            logger.info("Creating collection with placeholder document to ensure schema fields are created")
            placeholder_doc = Document(
                page_content="__placeholder__",
                metadata={
                    "category": "__placeholder__",
                    "difficulty": "__placeholder__",
                    "dish_name": "__placeholder__",
                    "user_id": "__placeholder__",
                    "parent_id": "__placeholder__",
                    "source": "__placeholder__",
                    "data_source": "__placeholder__",
                    "source_type": "__placeholder__",
                    "is_dish_index": False,
                }
            )
            vector_store = Milvus.from_documents(
                documents=[placeholder_doc],
                embedding=embeddings,
                **vector_store_kwargs,
            )
            # Delete the placeholder document
            try:
                vector_store.col.delete(expr='text == "__placeholder__"')  # type: ignore
                logger.info("Placeholder document deleted, empty collection with schema ready")
            except Exception as e:
                logger.warning(f"Failed to delete placeholder document: {e}")
        
        logger.info(f"Successfully created and populated Milvus collection: {collection_name}")
    else:
        logger.info(f"Connecting to existing Milvus collection: {collection_name}")
        vector_store_kwargs = _build_vector_store_kwargs(
            collection_name=collection_name,
            connection_args=connection_args,
            use_hybrid_search=use_hybrid_search,
        )
        vector_store = Milvus(
            embedding_function=embeddings,
            **vector_store_kwargs,
        )
        logger.info(f"Successfully connected to Milvus collection: {collection_name}")
        
    return vector_store
