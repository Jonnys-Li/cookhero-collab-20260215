# scripts/test_rag.py
import logging
import os, sys
from app.rag.rag_service import RAGService
from dotenv import load_dotenv

# --- Setup Logging ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Load environment variables ---
load_dotenv()

def test_rag_service():
    """
    Tests the RAGService by asking a sample question.
    """
    logger.info("--- Starting RAG Service Test ---")

    # Instantiate the RAGService.
    # This will automatically trigger the knowledge base loading and module initialization.
    try:
        rag_service = RAGService()
    except Exception as e:
        logger.error(f"Failed to initialize RAGService: {e}")
        return

    sample_questions = [
        "你好",
        "给我推荐几个素菜。",
        "宫保鸡丁需要什么食材？",
        "如何腌制小黄瓜？",
        "我想学习做菜，厨房里需要准备哪些基本工具和材料？"
    ]

    for i, question in enumerate(sample_questions):
        logger.info(f"\n--- Question {i+1}: {question} ---")
        try:
            # Test streaming response
            logger.info("Streaming response:")
            response_chunks = rag_service.ask(question, stream=True)
            full_response = ""
            for chunk in response_chunks:
                print(chunk, end="", flush=True)
                full_response += chunk
            print("\n") # Newline after streaming
            # logger.info(f"Full streaming response received: {full_response[:200]}...") # Log partial response
            
            # Test non-streaming response
            # logger.info("Non-streaming response:")
            # non_stream_response = rag_service.ask(question, stream=False)
            # print(non_stream_response)
            
        except Exception as e:
            logger.error(f"Error asking question '{question}': {e}", exc_info=True)

    logger.info("--- RAG Service Test Finished ---")

if __name__ == "__main__":
    test_rag_service()
