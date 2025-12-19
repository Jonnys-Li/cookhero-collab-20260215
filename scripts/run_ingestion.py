# scripts/run_ingestion.py
"""
Data ingestion pipeline for CookHero.
Loads documents from local files, stores them in PostgreSQL,
and creates vector embeddings in Milvus.
"""

import asyncio
import logging
from pathlib import Path

from app.config import DefaultRAGConfig, settings
from app.database.session import init_db, close_db
from app.database.document_repository import document_repository
from scripts.howtocook_loader import HowToCookLoader
from app.rag.embeddings.embedding_factory import get_embedding_model
from app.rag.vector_stores.vector_store_factory import get_vector_store

# --- Setup Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def ingest_howtocook(config, embeddings) -> None:
    """
    Ingest HowToCook data (recipes + tips) into PostgreSQL and Milvus.
    """
    logger.info("=== Starting HowToCook Ingestion ===")

    # 1. Load documents from local files
    source_config = config.data_source.howtocook
    data_path = Path(config.paths.base_data_path) / source_config.path_suffix
    tips_path = Path(config.paths.base_data_path) / source_config.tips_path_suffix

    logger.info("Loading documents from: %s, %s", data_path, tips_path)
    
    loader = HowToCookLoader(
        data_path=str(data_path),
        tips_path=str(tips_path),
        headers_to_split_on=source_config.headers_to_split_on,
    )
    
    parsed_docs = loader.load_documents()
    logger.info("Parsed %d documents from local files", len(parsed_docs))

    # 2. Delete existing recipes documents from PostgreSQL
    logger.info("Clearing existing recipes documents from PostgreSQL...")
    deleted_count = await document_repository.delete_by_data_source("recipes")
    logger.info("Deleted %d existing documents", deleted_count)

    # 3. Insert documents into PostgreSQL
    logger.info("Inserting documents into PostgreSQL...")
    doc_dicts = [doc.to_dict() for doc in parsed_docs]
    await document_repository.create_batch(doc_dicts)
    logger.info("Inserted %d documents into PostgreSQL", len(parsed_docs))

    # 4. Create chunks for vector store
    logger.info("Creating chunks for vector indexing...")
    chunks = loader.create_chunks(parsed_docs)
    logger.info("Created %d chunks", len(chunks))

    # 5. Index chunks in Milvus (with force_rebuild=True)
    collection_name = config.vector_store.collection_names.get("recipes")
    if not collection_name:
        logger.error("Collection name for 'recipes' not found in config")
        return

    logger.info("Indexing chunks in Milvus collection: %s", collection_name)
    _ = get_vector_store(
        milvus_config=settings.database.milvus,
        collection_name=collection_name,
        embeddings=embeddings,
        chunks=chunks,
        force_rebuild=True,
    )
    logger.info("Successfully indexed %d chunks in Milvus", len(chunks))

    logger.info("=== HowToCook Ingestion Complete ===")


async def ensure_personal_collection(config, embeddings) -> None:
    """
    Ensure the personal documents collection exists in Milvus.
    Creates an empty collection if it doesn't exist.
    """
    collection_name = config.vector_store.collection_names.get("personal")
    if not collection_name:
        logger.warning("Personal collection not configured, skipping")
        return

    logger.info("Ensuring personal documents collection exists: %s", collection_name)
    _ = get_vector_store(
        milvus_config=settings.database.milvus,
        collection_name=collection_name,
        embeddings=embeddings,
        chunks=[],  # Empty - will create with placeholder if needed
        force_rebuild=False,  # Don't drop existing personal docs
    )
    logger.info("Personal documents collection ready")


async def main():
    """Main ingestion pipeline."""
    logger.info("=== Starting CookHero Data Ingestion Pipeline ===")

    config = DefaultRAGConfig

    # Initialize database
    logger.info("Initializing database...")
    await init_db()

    try:
        # Initialize embedding model
        logger.info("Initializing embedding model...")
        embeddings = get_embedding_model(config)

        # Ingest HowToCook data
        await ingest_howtocook(config, embeddings)

        # Ensure personal collection exists
        await ensure_personal_collection(config, embeddings)

        logger.info("=== CookHero Data Ingestion Pipeline Complete ===")
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
