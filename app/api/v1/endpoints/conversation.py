# app/api/v1/endpoints/conversation.py
"""
Conversation API endpoints for multi-turn chat with RAG integration.
"""

import asyncio
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.services.conversation_service import conversation_service

logger = logging.getLogger(__name__)
router = APIRouter()


class ImageData(BaseModel):
    """Image data for multimodal requests."""
    data: str  # Base64 encoded image data
    mime_type: str = "image/jpeg"  # MIME type of the image


class ConversationRequest(BaseModel):
    """Request model for conversation endpoint."""
    message: str
    conversation_id: Optional[str] = None
    stream: bool = True
    extra_options: Optional[Dict[str, Any]] = None  # e.g., {"web_search": true}
    images: Optional[List[ImageData]] = Field(
        default=None,
        description="List of images (base64 encoded) for multimodal understanding"
    )


class ConversationHistoryResponse(BaseModel):
    """Response model for conversation history."""
    conversation_id: str
    messages: list


class ConversationSummary(BaseModel):
    """Summary model for listing conversations."""
    id: str
    title: Optional[str] = None
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
    - `extra_options`: Optional features object, e.g., `{"web_search": true}`
    - `images`: Optional list of images for multimodal understanding
    
    **Response (SSE stream when stream=true):**
    ```
    data: {"type": "vision", "data": {"is_food_related": true, "intent": "...", "description": "..."}}
    data: {"type": "intent", "data": {"need_rag": true, "intent": "recipe_search", "reason": "..."}}
    data: {"type": "web_search", "data": {"confidence": 8, "reason": "...", "should_search": true}}
    data: {"type": "thinking", "content": "重写后的检索语句：番茄炒蛋的做法"}
    data: {"type": "text", "content": "..."}
    data: {"type": "sources", "data": [...]}
    data: {"type": "done", "conversation_id": "..."}
    ```
    """
    logger.info(f"Received conversation request: '{request.message[:50]}...', images={len(request.images) if request.images else 0}")
    
    # Convert images to service format
    images_data = None
    if request.images:
        images_data = [
            {"data": img.data, "mime_type": img.mime_type}
            for img in request.images
        ]
    
    async def stream_with_disconnect_detection() -> AsyncGenerator[str, None]:
        """Wrapper generator that detects client disconnection."""
        try:
            async for chunk in conversation_service.chat(
                message=request.message,
                conversation_id=request.conversation_id,
                user_id=getattr(http_request.state, "user_id", None),
                stream=True,
                extra_options=request.extra_options,
                images=images_data,
            ):
                # Check if client is still connected
                if await http_request.is_disconnected():
                    logger.info("Client disconnected, stopping stream")
                    break
                yield chunk
        except asyncio.CancelledError:
            logger.info("Stream cancelled by client")
            raise
        except Exception as e:
            logger.error(f"Stream error: {e}", exc_info=True)
            raise
    
    try:
        if request.stream:
            return StreamingResponse(
                stream_with_disconnect_detection(),
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
                extra_options=request.extra_options,
                images=images_data,
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


class UpdateTitleRequest(BaseModel):
    """Request model for updating conversation title."""
    title: str


@router.put("/conversation/{conversation_id}/title")
async def update_conversation_title(conversation_id: str, request: UpdateTitleRequest):
    """
    Update the title of a conversation.
    
    **Parameters:**
    - `conversation_id`: The ID of the conversation
    - `title`: The new title for the conversation
    """
    success = await conversation_service.update_conversation_title(conversation_id, request.title)
    
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    return {"message": "Title updated successfully"}


class ConversationListResponse(BaseModel):
    """Response model for listing conversations."""
    conversations: list[ConversationSummary]
    total_count: int
    limit: int
    offset: int


@router.get("/conversation")
async def list_conversations(
    http_request: Request,
    limit: int = 50,
    offset: int = 0,
) -> ConversationListResponse:
    """List all conversations for the current user (PostgreSQL store).
    
    **Query Parameters:**
    - `limit`: Maximum number of conversations to return (default: 50)
    - `offset`: Number of conversations to skip (default: 0)
    """
    conversations, total_count = await conversation_service.list_conversations(
        user_id=getattr(http_request.state, "user_id", None),
        limit=limit,
        offset=offset,
    )
    return ConversationListResponse(
        conversations=[ConversationSummary(**c) for c in conversations],
        total_count=total_count,
        limit=limit,
        offset=offset,
    )
