# scripts/run_ingestion.py
import logging

from app.core.config_loader import DefaultRAGConfig
from app.rag.data_sources.howtocook_data_source import HowToCookDataSource
from app.rag.embeddings.embedding_factory import get_embedding_model
from app.rag.vector_stores.vector_store_factory import get_vector_store

# --- Setup Logging ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    """
    Main function to run the data ingestion and indexing pipeline.
    This script will drop the existing Milvus collection and rebuild it.
    """
    logger.info("--- Starting CookHero Data Ingestion Pipeline ---")

    config = DefaultRAGConfig
    
    # 1. Data Source and Preparation
    logger.info("Preparing data from source...")
    data_source = HowToCookDataSource(
        data_path=config.paths.data_path,
        headers_to_split_on=config.data_source.howtocook.headers_to_split_on
    )
    child_chunks = data_source.get_chunks()
    logger.info("Data preparation complete.")

    # 2. Embedding Model
    logger.info("Initializing embedding model...")
    embeddings = get_embedding_model(config)
    
    # 3. Vector Store
    logger.info("Building and populating vector store...")
    _ = get_vector_store(
        config=config,
        embeddings=embeddings,
        chunks=child_chunks,
        force_rebuild=True
    )
    
    logger.info("--- CookHero Data Ingestion Pipeline Finished ---")
    logger.info(f"Milvus collection '{config.vector_store.collection_name}' is ready.")

if __name__ == "__main__":
    main()
