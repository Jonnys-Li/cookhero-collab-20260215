# app/api/v1/endpoints/conversation.py
"""
Conversation API endpoints for multi-turn chat with RAG integration.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.conversation_service import conversation_service

logger = logging.getLogger(__name__)
router = APIRouter()


class ConversationRequest(BaseModel):
    """Request model for conversation endpoint."""
    message: str
    conversation_id: Optional[str] = None
    stream: bool = True


class ConversationHistoryResponse(BaseModel):
    """Response model for conversation history."""
    conversation_id: str
    messages: list


class ConversationSummary(BaseModel):
    """Summary model for listing conversations."""
    id: str
    created_at: str
    updated_at: str
    message_count: int
    last_message_preview: str | None = None


@router.post("/conversation")
async def conversation(request: ConversationRequest, http_request: Request):
    """
    Handle a conversation message with optional RAG integration.
    
    The endpoint automatically detects whether the query needs knowledge 
    base retrieval (RAG) or can be answered directly by the LLM.
    
    **Request Body:**
    - `message`: The user's input message
    - `conversation_id`: Optional ID for continuing a conversation
    - `stream`: Whether to stream the response (default: true)
    
    **Response (SSE stream when stream=true):**
    ```
    data: {"type": "intent", "data": {"need_rag": true, "intent": "recipe_search", "reason": "..."}}
    data: {"type": "thinking", "content": "重写后的检索语句：番茄炒蛋的做法"}
    data: {"type": "text", "content": "..."}
    data: {"type": "sources", "data": [...]}
    data: {"type": "done", "conversation_id": "..."}
    ```
    """
    logger.info(f"Received conversation request: '{request.message[:50]}...'")
    
    try:
        if request.stream:
            return StreamingResponse(
                conversation_service.chat(
                    message=request.message,
                    conversation_id=request.conversation_id,
                    user_id=getattr(http_request.state, "user_id", None),
                    stream=True,
                ),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no"  # Disable nginx buffering
                }
            )
        else:
            # Non-streaming: collect all chunks
            full_response = ""
            sources = []
            conv_id = None
            intent_data = None
            
            async for event in conversation_service.chat(
                message=request.message,
                conversation_id=request.conversation_id,
                user_id=getattr(http_request.state, "user_id", None),
                stream=False,
            ):
                # Parse SSE event
                if event.startswith("data: "):
                    import json
                    data = json.loads(event[6:].strip())
                    
                    if data["type"] == "text":
                        full_response += data["content"]
                    elif data["type"] == "sources":
                        sources = data["data"]
                    elif data["type"] == "done":
                        conv_id = data["conversation_id"]
                    elif data["type"] == "intent":
                        intent_data = data["data"]
                    elif data["type"] == "thinking":
                        # Thinking events are informational; no aggregation needed for non-streaming mode
                        continue
            
            return {
                "conversation_id": conv_id,
                "response": full_response,
                "sources": sources,
                "intent": intent_data
            }
            
    except Exception as e:
        logger.error(f"Error processing conversation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An error occurred while processing your request.")


@router.get("/conversation/{conversation_id}")
async def get_conversation_history(conversation_id: str):
    """
    Get the history of a conversation.
    
    **Parameters:**
    - `conversation_id`: The ID of the conversation
    
    **Response:**
    ```json
    {
        "conversation_id": "...",
        "messages": [
            {
                "role": "user",
                "content": "...",
                "timestamp": "...",
                "sources": null,
                "intent": null
            },
            {
                "role": "assistant",
                "content": "...",
                "timestamp": "...",
                "sources": [...],
                "intent": "recipe_search"
            }
        ]
    }
    ```
    """
    history = await conversation_service.get_conversation_history(conversation_id)
    
    if history is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    return ConversationHistoryResponse(
        conversation_id=conversation_id,
        messages=history
    )


@router.delete("/conversation/{conversation_id}")
async def clear_conversation(conversation_id: str):
    """
    Clear/delete a conversation.
    
    **Parameters:**
    - `conversation_id`: The ID of the conversation to delete
    """
    success = await conversation_service.clear_conversation(conversation_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    return {"message": "Conversation cleared successfully"}


@router.get("/conversation")
async def list_conversations(http_request: Request) -> list[ConversationSummary]:
    """List all conversations for the current user (PostgreSQL store)."""
    conversations = await conversation_service.list_conversations(user_id=getattr(http_request.state, "user_id", None))
    return [ConversationSummary(**c) for c in conversations]
