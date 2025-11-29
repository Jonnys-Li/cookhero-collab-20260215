# scripts/run_ingestion.py
import logging
import os
from app.rag.config import DefaultRAGConfig
from app.rag.data_preparation import DataPreparationModule
from app.rag.index_construction import IndexConstructionModule

# --- Setup Logging ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    """
    Main function to run the data ingestion and indexing pipeline.
    """
    logger.info("--- Starting CookHero Data Ingestion Pipeline ---")

    # Use the default configuration
    config = DefaultRAGConfig
    
    # --- 1. Data Preparation ---
    logger.info(f"Loading data from: {config.DATA_PATH}")
    data_prep_module = DataPreparationModule(
        data_path=config.DATA_PATH,
        headers_to_split_on=config.HEADERS_TO_SPLIT_ON
    )
    # Load documents and create chunks
    data_prep_module.load_and_process_documents()

    # Get the processed chunks for indexing
    child_chunks = data_prep_module.child_chunks
    if not child_chunks:
        logger.error("No chunks were created from the data. Aborting ingestion.")
        return

    # Log statistics
    stats = data_prep_module.get_statistics()
    logger.info(f"Data Preparation Stats: {stats}")
    
    # --- 2. Index Construction ---
    logger.info("Initializing index construction module...")
    index_module = IndexConstructionModule(
        config=config
    )
    
    # This will either build a new index and save it, or load the existing one.
    # Since we might be changing embedding models, let's force a rebuild for now.
    # A more robust solution would be to check if the config has changed.
    # For now, to test the new remote embedding, we should delete the old index first.
    logger.info("Forcing rebuild of index to ensure correct embedding model is used.")
    index_module._build_new_index(chunks=child_chunks)

    logger.info("--- CookHero Data Ingestion Pipeline Finished ---")
    logger.info(f"Vector index is ready at: {os.path.abspath(config.INDEX_SAVE_PATH)}")

if __name__ == "__main__":
    main()
