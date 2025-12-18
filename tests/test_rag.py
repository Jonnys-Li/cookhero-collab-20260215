# scripts/test_rag.py
import asyncio
import logging
# --- Setup Logging ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from app.services.rag_service import rag_service_instance

async def test_rag_service():
    """
    Tests the RAGService by asking a sample question.
    """
    logger.info("--- Starting RAG Service Test ---")

    # The RAGService is now a singleton that initializes itself on first import.
    # The config loader handles the API key check.

    sample_questions = [
        "皮蛋瘦肉粥怎么做？",
        # "请推荐几道简单的素菜。",
        # "皮蛋有哪些做法？",
        "皮蛋粥怎么做？",
    ]

    for i, question in enumerate(sample_questions):
        logger.info(f"\n--- Question {i+1}: {question} ---")
        try:
            logger.info("Streaming response:")
            response = await rag_service_instance.ask_with_generation(question, stream=False)
            print(response)
            print("\n")
            
        except Exception as e:
            logger.error(f"Error asking question '{question}': {e}", exc_info=True)

    logger.info("--- RAG Service Test Finished ---")

if __name__ == "__main__":
    asyncio.run(test_rag_service())
