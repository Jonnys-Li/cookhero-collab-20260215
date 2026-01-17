# app/api/v1/endpoints/agent.py
"""
Agent API endpoints for tool-augmented chat.
Independent from the conversation endpoints, designed for agent-based interactions.
"""

import asyncio
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from app.config import settings
from app.agent.service import agent_service
from app.agent.registry import AgentHub
from app.security.dependencies import check_message_security

logger = logging.getLogger(__name__)
router = APIRouter()

# Constants for input validation
MAX_MESSAGE_LENGTH = settings.MAX_MESSAGE_LENGTH  # 10000 characters


class ToolInfo(BaseModel):
    """Tool information for the tools list endpoint."""

    name: str
    description: str
    type: str  # "builtin" | "mcp"
    source: Optional[str] = None  # MCP server name for MCP tools


class ToolsListResponse(BaseModel):
    """Response model for the tools list endpoint."""

    tools: List[ToolInfo]
    mcp_servers: List[str]


class AgentChatRequest(BaseModel):
    """Request model for agent chat endpoint."""

    message: str = Field(..., max_length=MAX_MESSAGE_LENGTH)
    session_id: Optional[str] = None
    agent_name: str = Field(default="default", max_length=100)
    stream: bool = True
    selected_tools: Optional[List[str]] = None  # User-selected tools

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        """Validate message content."""
        if not v or not v.strip():
            raise ValueError("消息不能为空")
        if len(v) > MAX_MESSAGE_LENGTH:
            raise ValueError(f"消息长度超过限制 ({MAX_MESSAGE_LENGTH} 字符)")
        return v


class AgentSessionResponse(BaseModel):
    """Response model for agent session."""

    id: str
    user_id: str
    title: Optional[str] = None
    created_at: str
    updated_at: str
    message_count: int


class AgentMessageResponse(BaseModel):
    """Response model for agent message."""

    id: str
    session_id: str
    role: str
    content: str
    created_at: str
    trace: Optional[List[Dict[str, Any]]] = None
    thinking_duration_ms: Optional[int] = None
    answer_duration_ms: Optional[int] = None


class AgentSessionListResponse(BaseModel):
    """Response model for listing agent sessions."""

    sessions: List[AgentSessionResponse]
    total_count: int
    limit: int
    offset: int


class AgentHistoryResponse(BaseModel):
    """Response model for agent session history."""

    session_id: str
    messages: List[AgentMessageResponse]


@router.get("/agent/tools")
async def list_available_tools(http_request: Request) -> ToolsListResponse:
    """
    List all available tools and MCP servers.

    Returns a list of all registered tools (both builtin and MCP) along with
    the list of registered MCP servers.

    **Response:**
    ```json
    {
        "tools": [
            {
                "name": "calculator",
                "description": "执行数学计算...",
                "type": "builtin",
                "source": null
            },
            {
                "name": "mcp_amap_poi_search",
                "description": "搜索兴趣点...",
                "type": "mcp",
                "source": "amap"
            }
        ],
        "mcp_servers": ["amap"]
    }
    ```
    """
    # Check authentication
    user_id = getattr(http_request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="需要登录")

    tools: List[ToolInfo] = []

    # Get all registered tools with their info
    for tool_info in AgentHub.list_tools_info():
        tools.append(
            ToolInfo(
                name=tool_info["name"],
                description=tool_info["description"],
                type=tool_info["type"],
                source=tool_info.get("source"),
            )
        )

    # Get MCP servers
    mcp_provider_any = AgentHub.get_provider("mcp")  # type: ignore[assignment]
    mcp_servers = (
        getattr(mcp_provider_any, "list_servers")()
        if hasattr(mcp_provider_any, "list_servers")
        else []
    )

    return ToolsListResponse(tools=tools, mcp_servers=mcp_servers)


@router.post("/agent/chat")
async def agent_chat(request: AgentChatRequest, http_request: Request):
    """
    Handle a chat message with the Agent system.

    The Agent can use tools and skills to answer questions.
    This is independent from the RAG-based conversation endpoint.

    **Request Body:**
    - `message`: The user's input message
    - `session_id`: Optional ID for continuing a session
    - `agent_name`: Name of the agent to use (default: "default")
    - `stream`: Whether to stream the response (default: true)
    - `selected_tools`: Optional list of tool names to use (default: all tools)

    **Response (SSE stream when stream=true):**
    ```
    data: {"type": "session", "session_id": "...", "agent_name": "..."}
    data: {"type": "text", "content": "..."}
    data: {"type": "tool_call", "id": "...", "name": "...", "arguments": {...}}
    data: {"type": "tool_result", "name": "...", "success": true, "result": "..."}
    data: {"type": "trace", "iteration": 1, "action": "...", ...}
    data: {"type": "done", "session_id": "..."}
    ```
    """
    # ==========================================================================
    # Security Check: Use unified security check function
    # ==========================================================================
    secured_message = await check_message_security(request.message, http_request)

    logger.info(
        f"Agent chat request: '{secured_message[:50]}...', agent={request.agent_name}"
    )

    # Get user information from request state
    user_id = getattr(http_request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="需要登录")

    async def stream_with_disconnect_detection() -> AsyncGenerator[str, None]:
        """Wrapper generator that detects client disconnection."""
        try:
            async for chunk in agent_service.chat(
                session_id=request.session_id,
                user_id=user_id,
                message=secured_message,
                agent_name=request.agent_name,
                streaming=request.stream,
                selected_tools=request.selected_tools,
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
                    "X-Accel-Buffering": "no",  # Disable nginx buffering
                },
            )
        else:
            # Non-streaming: collect all chunks
            full_response = ""
            session_id = None
            tool_results = []

            async for event in agent_service.chat(
                session_id=request.session_id,
                user_id=user_id,
                message=secured_message,
                agent_name=request.agent_name,
                streaming=False,
                selected_tools=request.selected_tools,
            ):
                # Parse SSE event
                if event.startswith("data: "):
                    import json

                    data = json.loads(event[6:].strip())

                    if data["type"] == "text":
                        full_response += data.get("content", "")
                    elif data["type"] == "session":
                        session_id = data.get("session_id")
                    elif data["type"] == "tool_result":
                        tool_results.append(data)
                    elif data["type"] == "done":
                        session_id = data.get("session_id", session_id)

            return {
                "session_id": session_id,
                "response": full_response,
                "tool_results": tool_results,
            }

    except Exception as e:
        logger.error(f"Error processing agent chat: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="处理请求时发生错误")


@router.get("/agent/session/{session_id}")
async def get_agent_session(session_id: str, http_request: Request):
    """
    Get an agent session by ID.

    **Parameters:**
    - `session_id`: The ID of the session

    **Response:**
    ```json
    {
        "id": "...",
        "user_id": "...",
        "agent_name": "...",
        "created_at": "...",
        "updated_at": "...",
        "message_count": 10
    }
    ```
    """
    session = await agent_service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    # Verify user owns this session
    user_id = getattr(http_request.state, "user_id", None)
    if user_id and session.get("user_id") != str(user_id):
        raise HTTPException(status_code=403, detail="无权访问此会话")

    return session


@router.get("/agent/session/{session_id}/messages")
async def get_agent_session_messages(
    session_id: str,
    http_request: Request,
    limit: Optional[int] = None,
):
    """
    Get all messages in an agent session.

    **Parameters:**
    - `session_id`: The ID of the session
    - `limit`: Optional limit on number of messages to return

    **Response:**
    ```json
    {
        "session_id": "...",
        "messages": [
            {
                "id": "...",
                "role": "user",
                "content": "...",
                "created_at": "...",
                "trace": null,
                "tool_calls": null
            },
            ...
        ]
    }
    ```
    """
    # First verify session exists and user has access
    session = await agent_service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    user_id = getattr(http_request.state, "user_id", None)
    if user_id and session.get("user_id") != str(user_id):
        raise HTTPException(status_code=403, detail="无权访问此会话")

    messages = await agent_service.get_messages(session_id, limit)
    return AgentHistoryResponse(
        session_id=session_id,
        messages=[AgentMessageResponse(**msg) for msg in messages],
    )


@router.delete("/agent/session/{session_id}")
async def delete_agent_session(session_id: str, http_request: Request):
    """
    Delete an agent session.

    **Parameters:**
    - `session_id`: The ID of the session to delete
    """
    # First verify session exists and user has access
    session = await agent_service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    user_id = getattr(http_request.state, "user_id", None)
    if user_id and session.get("user_id") != str(user_id):
        raise HTTPException(status_code=403, detail="无权删除此会话")

    success = await agent_service.delete_session(session_id)
    if not success:
        raise HTTPException(status_code=500, detail="删除会话失败")

    return {"message": "Session deleted successfully"}


class UpdateSessionTitleRequest(BaseModel):
    """Request model for updating session title."""

    title: str = Field(..., max_length=255)


@router.patch("/agent/session/{session_id}/title")
async def update_agent_session_title(
    session_id: str, request: UpdateSessionTitleRequest, http_request: Request
):
    """
    Update an agent session's title.

    **Parameters:**
    - `session_id`: The ID of the session to update

    **Request Body:**
    - `title`: The new title for the session
    """
    # First verify session exists and user has access
    session = await agent_service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    user_id = getattr(http_request.state, "user_id", None)
    if user_id and session.get("user_id") != str(user_id):
        raise HTTPException(status_code=403, detail="无权修改此会话")

    success = await agent_service.update_session_title(session_id, request.title)
    if not success:
        raise HTTPException(status_code=500, detail="更新会话标题失败")

    return {"message": "Title updated successfully", "title": request.title}


@router.get("/agent/sessions")
async def list_agent_sessions(
    http_request: Request,
    limit: int = 50,
    offset: int = 0,
) -> AgentSessionListResponse:
    """
    List all agent sessions for the current user.

    **Query Parameters:**
    - `limit`: Maximum number of sessions to return (default: 50)
    - `offset`: Number of sessions to skip (default: 0)
    """
    user_id = getattr(http_request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="需要登录")

    sessions, total_count = await agent_service.list_sessions(
        user_id=user_id,
        limit=limit,
        offset=offset,
    )

    return AgentSessionListResponse(
        sessions=[AgentSessionResponse(**s) for s in sessions],
        total_count=total_count,
        limit=limit,
        offset=offset,
    )
