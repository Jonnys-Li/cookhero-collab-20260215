# scripts/run_ingestion.py
import logging
from pathlib import Path

from app.core.config_loader import DefaultRAGConfig
from app.rag.data_sources.howtocook_data_source import HowToCookDataSource
from app.rag.data_sources.tips_data_source import TipsDataSource
from app.rag.data_sources.generic_text_data_source import GenericTextDataSource
from app.rag.embeddings.embedding_factory import get_embedding_model
from app.rag.vector_stores.vector_store_factory import get_vector_store
from app.core.rag_config import RAGConfig

# --- Setup Logging ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def ingest_data_source(config: RAGConfig, embeddings, source_name: str, data_source_class, data_source_config):
    """
    Ingests data from a single data source into a specified Milvus collection.
    """
    logger.info(f"--- Starting Ingestion for Source: {source_name} ---")

    # 1. Data Source and Preparation
    data_path = Path(config.paths.base_data_path) / data_source_config.path_suffix
    logger.info(f"Preparing data from source path: {data_path}")
    
    # Dynamically create the data source instance with the correct parameters
    if hasattr(data_source_config, 'window_size'):
        # For GenericTextDataSource or any other with window_size
        data_source = data_source_class(
            data_path=str(data_path),
            window_size=data_source_config.window_size
        )
    elif hasattr(data_source_config, 'headers_to_split_on'):
        # For HowToCookDataSource and TipsDataSource
        data_source = data_source_class(
            data_path=str(data_path),
            headers_to_split_on=data_source_config.headers_to_split_on
        )
    else:
        # Default case, if no specific config is found
        data_source = data_source_class(data_path=str(data_path))

    child_chunks = data_source.get_chunks()
    logger.info(f"Data preparation complete for {source_name}.")

    # 2. Get Collection Name
    collection_name = config.vector_store.collection_names.get(source_name)
    if not collection_name:
        logger.error(f"Collection name for source '{source_name}' not found in config. Skipping.")
        return

    # 3. Vector Store Ingestion
    logger.info(f"Building and populating vector store for collection: '{collection_name}'")
    _ = get_vector_store(
        vs_config=config.vector_store,
        collection_name=collection_name,
        embeddings=embeddings,
        chunks=child_chunks,
        force_rebuild=True
    )
    logger.info(f"--- Ingestion for Source: {source_name} Finished ---")


def main():
    """
    Main function to run the data ingestion and indexing pipeline for all configured sources.
    This script will drop and rebuild the existing Milvus collections.
    """
    logger.info("--- Starting CookHero Data Ingestion Pipeline ---")

    config = DefaultRAGConfig

    # Initialize embedding model once
    logger.info("Initializing embedding model...")
    embeddings = get_embedding_model(config)

    # Ingest HowToCook recipes
    ingest_data_source(
        config=config,
        embeddings=embeddings,
        source_name="recipes",
        data_source_class=HowToCookDataSource,
        data_source_config=config.data_source.howtocook
    )

    # Ingest Tips
    ingest_data_source(
        config=config,
        embeddings=embeddings,
        source_name="tips",
        data_source_class=TipsDataSource,
        data_source_config=config.data_source.tips
    )
    
    # Ingest Generic Text documents
    ingest_data_source(
        config=config,
        embeddings=embeddings,
        source_name="generic_text",
        data_source_class=GenericTextDataSource,
        data_source_config=config.data_source.generic_text
    )

    logger.info("--- CookHero Data Ingestion Pipeline Finished ---")


if __name__ == "__main__":
    main()
