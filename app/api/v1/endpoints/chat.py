# app/api/v1/endpoints/chat.py
import logging
from fastapi import APIRouter
from pydantic import BaseModel
from starlette.responses import StreamingResponse

from app.services.rag_service import rag_service_instance

logger = logging.getLogger(__name__)
router = APIRouter()

class ChatRequest(BaseModel):
    """Request model for the chat endpoint."""
    query: str
    stream: bool = True

@router.post("/chat")
async def chat(request: ChatRequest):
    """
    Handles a user's chat query, using the RAG service to generate a response.
    """
    logger.info(f"Received chat request with query: '{request.query}'")
    
    try:
        response_generator = rag_service_instance.ask_with_generation(request.query, stream=request.stream)
        
        if request.stream:
            # For streaming responses
            return StreamingResponse(response_generator, media_type="text/plain")
        else:
            # For non-streaming responses
            return {"response": response_generator}
            
    except Exception as e:
        logger.error(f"Error processing chat request: {e}", exc_info=True)
        return {"error": "An error occurred while processing your request."}, 500
