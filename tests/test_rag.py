# scripts/test_rag.py
import logging
# --- Setup Logging ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from app.rag.rag_service import rag_service_instance

def test_rag_service():
    """
    Tests the RAGService by asking a sample question.
    """
    logger.info("--- Starting RAG Service Test ---")

    # The RAGService is now a singleton that initializes itself on first import.
    # The config loader handles the API key check.

    sample_questions = [
        # "皮蛋瘦肉粥怎么做？",
        # "皮蛋瘦肉粥需要准备哪些食材以及厨房用具？",
        # "皮蛋瘦肉粥的做法",
        # "需要一些可以自制的甜品推荐",
        "推荐一些名字比较好听的菜品",
        "平时在家做家常菜，厨房里需要常备哪些？"
    ]

    for i, question in enumerate(sample_questions):
        logger.info(f"\n--- Question {i+1}: {question} ---")
        try:
            logger.info("Streaming response:")
            response_chunks = rag_service_instance.ask(question, stream=True)
            full_response = ""
            for chunk in response_chunks:
                print(chunk, end="", flush=True)
                full_response += chunk
            print("\n")
            
        except Exception as e:
            logger.error(f"Error asking question '{question}': {e}", exc_info=True)

    logger.info("--- RAG Service Test Finished ---")

if __name__ == "__main__":
    test_rag_service()
