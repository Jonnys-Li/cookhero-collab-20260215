# app/api/v1/endpoints/agent.py
"""
Agent API endpoints for tool-augmented chat.
Independent from the conversation endpoints, designed for agent-based interactions.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import uuid
from datetime import date, datetime, timedelta
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator, HttpUrl

from app.config import settings
from app.agent.service import agent_service
from app.agent.registry import AgentHub
from app.security.dependencies import check_message_security
from app.services.mcp_service import mcp_service
from app.services.emotion_budget_service import emotion_budget_service
from app.services.subagent_service import subagent_service
from app.diet.service import diet_service

logger = logging.getLogger(__name__)
router = APIRouter()

# Constants for input validation
MAX_MESSAGE_LENGTH = settings.MAX_MESSAGE_LENGTH  # 10000 characters
MAX_IMAGES = 4
MAX_IMAGE_SIZE_MB = 10.0
SUPPORTED_IMAGE_FORMATS = ["image/jpeg", "image/png", "image/gif", "image/webp"]
EMOTION_DEMO_METADATA_KEY = "emotion_demo_state"
EMOTION_FOLLOW_UP_COOLDOWN_SECONDS = 180


class ToolSchema(BaseModel):
    """Tool schema for the tools API."""

    name: str
    description: str


class ServerInfo(BaseModel):
    """Server info for the tools API."""

    name: str
    type: str  # "local" or "mcp"
    tools: List[ToolSchema]


class ToolsListResponse(BaseModel):
    """Response model for the tools list endpoint."""

    servers: List[ServerInfo]


class MCPServerRequest(BaseModel):
    """Request model for creating MCP server."""

    name: str = Field(..., min_length=2, max_length=64)
    endpoint: HttpUrl
    auth_header_name: Optional[str] = Field(default=None, max_length=128)
    auth_token: Optional[str] = None


class MCPServerResponse(BaseModel):
    """Response model for MCP server info."""

    id: str
    name: str
    endpoint: str
    auth_header_name: Optional[str] = None
    auth_token: Optional[str] = None
    enabled: bool
    created_at: str
    updated_at: str
    loaded_tools_count: Optional[int] = None
    loaded_tools: Optional[List[str]] = None


class MCPServerListResponse(BaseModel):
    """Response model for MCP server list."""

    servers: List[MCPServerResponse]


class MCPServerUpdateRequest(BaseModel):
    """Request model for updating MCP server."""

    endpoint: Optional[HttpUrl] = None
    auth_header_name: Optional[str] = Field(default=None, max_length=128)
    auth_token: Optional[str] = None
    enabled: Optional[bool] = None


class ImageData(BaseModel):
    """Image data for multimodal requests."""

    data: str  # Base64 encoded image data
    mime_type: str = "image/jpeg"

    @field_validator("mime_type")
    @classmethod
    def validate_mime_type(cls, v: str) -> str:
        """Validate image MIME type."""
        if v not in SUPPORTED_IMAGE_FORMATS:
            raise ValueError(
                f"不支持的图片格式: {v}。支持的格式: {SUPPORTED_IMAGE_FORMATS}"
            )
        return v

    @field_validator("data")
    @classmethod
    def validate_data(cls, v: str) -> str:
        """Validate base64 image data size."""
        try:
            # Decode to check size (base64 is ~33% larger than binary)
            decoded_size = len(base64.b64decode(v))
            max_size = MAX_IMAGE_SIZE_MB * 1024 * 1024
            if decoded_size > max_size:
                raise ValueError(f"图片大小超过限制 ({MAX_IMAGE_SIZE_MB}MB)")
        except Exception as e:
            if "图片大小超过限制" in str(e):
                raise
            raise ValueError("无效的 base64 图片数据")
        return v


class AgentChatRequest(BaseModel):
    """Request model for agent chat endpoint."""

    message: str = Field(..., max_length=MAX_MESSAGE_LENGTH)
    images: Optional[List[ImageData]] = Field(default=None, max_length=MAX_IMAGES)
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
    last_message_preview: Optional[str] = None


class AgentMessageResponse(BaseModel):
    """Response model for agent message."""

    id: str
    session_id: str
    role: str
    content: str
    created_at: str
    trace: Optional[List[Dict[str, Any]]] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    tool_name: Optional[str] = None
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


class ApplyEmotionBudgetAdjustRequest(BaseModel):
    """Apply emotion-budget adjustment action from chat card."""

    session_id: str
    action_id: str
    delta_calories: int = Field(..., description="仅支持 50/100/150")
    mode: str = Field(..., pattern="^(user_select|auto_timeout)$")
    reason: Optional[str] = Field(default=None, max_length=200)

    @field_validator("delta_calories")
    @classmethod
    def validate_delta_calories(cls, value: int) -> int:
        if value not in {50, 100, 150}:
            raise ValueError("delta_calories 仅支持 50/100/150")
        return value


class ApplyEmotionBudgetAdjustResponse(BaseModel):
    """Response payload for emotion-budget adjustment result."""

    action_id: str
    requested: int
    applied: Optional[int] = None
    capped: bool
    effective_goal: Optional[int] = None
    goal_source: Optional[str] = None
    goal_seeded: Optional[bool] = None
    used_provider: str
    mode: str
    message: str


class ApplySmartActionRequest(BaseModel):
    """Apply action from smart recommendation card."""

    session_id: str
    action_id: str
    action_kind: str = Field(
        ...,
        pattern=(
            "^("
            "apply_budget_adjust|"
            "apply_next_meal_plan|"
            "fetch_weekly_progress|"
            "submit_plan_profile|"
            "apply_week_plan"
            ")$"
        ),
    )
    mode: str = Field(..., pattern="^(user_select|timeout_suggest_only)$")
    payload: Optional[Dict[str, Any]] = None
    reason: Optional[str] = Field(default=None, max_length=200)


class ApplySmartActionResponse(BaseModel):
    """Response payload for smart recommendation action."""

    action_id: str
    action_kind: str
    mode: str
    applied: bool
    used_provider: str
    message: str
    result: Optional[Dict[str, Any]] = None


def _parse_trace_step(raw: Any) -> Optional[dict[str, Any]]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, dict):
            return parsed
    return None


def _extract_trace_content(raw_content: Any) -> Optional[dict[str, Any]]:
    if isinstance(raw_content, dict):
        return raw_content
    if isinstance(raw_content, str):
        try:
            parsed = json.loads(raw_content)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return None
    return None


async def _find_emotion_ui_action(
    session_id: str,
    action_id: str,
) -> Optional[dict[str, Any]]:
    messages = await agent_service.repository.get_messages(session_id, limit=200)
    for msg in reversed(messages):
        if msg.role != "assistant" or not msg.trace:
            continue
        for raw_step in msg.trace:
            step = _parse_trace_step(raw_step)
            if not step:
                continue
            if step.get("action") != "ui_action":
                continue
            content = _extract_trace_content(step.get("content"))
            if not content:
                continue
            if content.get("action_type") != "emotion_budget_adjust":
                continue
            if content.get("action_id") == action_id:
                return content
    return None


async def _find_smart_ui_action(
    session_id: str,
    action_id: str,
) -> Optional[dict[str, Any]]:
    allowed_action_types = {
        "smart_recommendation_card",
        "meal_plan_planmode_card",
        "meal_plan_preview_card",
    }
    messages = await agent_service.repository.get_messages(session_id, limit=200)
    for msg in reversed(messages):
        if msg.role != "assistant" or not msg.trace:
            continue
        for raw_step in msg.trace:
            step = _parse_trace_step(raw_step)
            if not step:
                continue
            if step.get("action") != "ui_action":
                continue
            content = _extract_trace_content(step.get("content"))
            if not content:
                continue
            if content.get("action_type") not in allowed_action_types:
                continue
            if content.get("action_id") != action_id:
                continue
            return content
    return None


async def _find_existing_emotion_action_result(
    session_id: str,
    action_id: str,
) -> Optional[dict[str, Any]]:
    messages = await agent_service.repository.get_messages(session_id, limit=200)
    for msg in reversed(messages):
        if msg.role != "assistant" or not msg.trace:
            continue
        for raw_step in msg.trace:
            step = _parse_trace_step(raw_step)
            if not step:
                continue
            if step.get("action") != "emotion_budget_adjust_result":
                continue
            content = _extract_trace_content(step.get("content"))
            if not content:
                continue
            if content.get("action_id") == action_id:
                return content
    return None


async def _find_existing_smart_action_result(
    session_id: str,
    action_id: str,
    action_kind: str,
) -> Optional[dict[str, Any]]:
    messages = await agent_service.repository.get_messages(session_id, limit=200)
    for msg in reversed(messages):
        if msg.role != "assistant" or not msg.trace:
            continue
        for raw_step in msg.trace:
            step = _parse_trace_step(raw_step)
            if not step:
                continue
            if step.get("action") != "smart_action_result":
                continue
            content = _extract_trace_content(step.get("content"))
            if not content:
                continue
            if content.get("action_id") != action_id:
                continue
            if content.get("action_kind") != action_kind:
                continue
            return content
    return None


@router.get("/agent/tools")
async def list_available_tools(http_request: Request) -> ToolsListResponse:
    """
    List all available tools grouped by server.

    Returns a unified structure where both builtin and MCP tools are grouped
    by their respective servers.

    **Response:**
    ```json
    {
        "servers": [
            {
                "name": "builtin",
                "type": "local",
                "tools": [
                    {"name": "calculator", "description": "执行数学计算..."}
                ]
            },
            {
                "name": "amap",
                "type": "mcp",
                "tools": [
                    {"name": "mcp_amap_poi_search", "description": "搜索兴趣点..."}
                ]
            }
        ]
    }
    ```
    """
    # Check authentication
    user_id = getattr(http_request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="需要登录")

    # Get unified server list from AgentHub
    servers_data = AgentHub.list_all_servers(user_id=user_id)
    servers_data = [s for s in servers_data if s.get("type") != "subagent"]

    servers = [
        ServerInfo(
            name=s["name"],
            type=s["type"],
            tools=[ToolSchema(**t) for t in s["tools"]],
        )
        for s in servers_data
    ]

    return ToolsListResponse(servers=servers)


@router.get("/agent/mcp-servers")
async def list_mcp_servers(http_request: Request) -> MCPServerListResponse:
    """List MCP servers for current user."""
    user_id = getattr(http_request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="需要登录")

    servers = await mcp_service.list_servers(user_id)
    return MCPServerListResponse(
        servers=[MCPServerResponse(**server.to_dict()) for server in servers]
    )


@router.post("/agent/mcp-servers", status_code=201)
async def create_mcp_server(
    payload: MCPServerRequest, http_request: Request
) -> MCPServerResponse:
    """Create MCP server and register immediately."""
    user_id = getattr(http_request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="需要登录")

    try:
        server, loaded_tools = await mcp_service.create_server(
            user_id=user_id,
            name=payload.name,
            endpoint=str(payload.endpoint),
            enabled=True,
            auth_header_name=payload.auth_header_name,
            auth_token=payload.auth_token,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return MCPServerResponse(
        **server.to_dict(),
        loaded_tools_count=len(loaded_tools),
        loaded_tools=loaded_tools,
    )


@router.patch("/agent/mcp-servers/{server_name}")
async def update_mcp_server(
    server_name: str,
    payload: MCPServerUpdateRequest,
    http_request: Request,
) -> MCPServerResponse:
    """Update MCP server configuration."""
    user_id = getattr(http_request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="需要登录")

    update_data = payload.model_dump(exclude_unset=True)
    update_auth = any(
        key in update_data for key in ("auth_header_name", "auth_token")
    )

    try:
        result = await mcp_service.update_server(
            user_id=user_id,
            name=server_name,
            endpoint=str(update_data["endpoint"]) if "endpoint" in update_data else None,
            enabled=update_data.get("enabled"),
            auth_header_name=update_data.get("auth_header_name"),
            auth_token=update_data.get("auth_token"),
            update_auth=update_auth,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not result:
        raise HTTPException(status_code=404, detail="MCP server not found")

    server, loaded_tools = result
    return MCPServerResponse(
        **server.to_dict(),
        loaded_tools_count=len(loaded_tools),
        loaded_tools=loaded_tools or None,
    )


@router.delete("/agent/mcp-servers/{server_name}")
async def delete_mcp_server(server_name: str, http_request: Request):
    """Delete MCP server configuration."""
    user_id = getattr(http_request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="需要登录")

    try:
        deleted = await mcp_service.delete_server(user_id, server_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not deleted:
        raise HTTPException(status_code=404, detail="MCP server not found")

    return {"message": "MCP server deleted successfully"}


@router.post("/agent/chat")
async def agent_chat(request: AgentChatRequest, http_request: Request):
    """
    Handle a chat message with the Agent system.

    The Agent can use tools and skills to answer questions.
    This is independent from the RAG-based conversation endpoint.

    **Request Body:**
    - `message`: The user's input message
    - `images`: Optional list of images (base64 encoded, max 4)
    - `session_id`: Optional ID for continuing a session
    - `agent_name`: Name of the agent to use (default: "default")
    - `stream`: Whether to stream the response (default: true)
    - `selected_tools`: Optional list of tool names to use (default: all tools)

    **Response (SSE stream when stream=true):**
    ```
    data: {"type": "session", "session_id": "...", "agent_name": "..."}
    data: {"type": "vision", "is_food_related": true, "description": "..."}
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

    # Convert images to dict format for service
    images_data = None
    if request.images:
        images_data = [
            {"data": img.data, "mime_type": img.mime_type} for img in request.images
        ]

    logger.info(
        f"Agent chat request: '{secured_message[:50]}...', agent={request.agent_name}, images={len(images_data) if images_data else 0}"
    )

    # Get user information from request state
    user_id = getattr(http_request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="需要登录")

    # Use queue-based approach to ensure backend continues even if client disconnects
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    async def process_in_background():
        """Background task that processes the chat and puts results in queue.

        This task runs independently from the client connection, ensuring
        messages are saved to database even if client refreshes/disconnects.
        """
        try:
            async for chunk in agent_service.chat(
                session_id=request.session_id,
                user_id=user_id,
                message=secured_message,
                agent_name=request.agent_name,
                streaming=request.stream,
                selected_tools=request.selected_tools,
                images=images_data,
            ):
                await queue.put(chunk)
        except Exception as e:
            logger.error(f"Background processing error: {e}", exc_info=True)
        finally:
            await queue.put(None)  # Signal completion

    async def stream_from_queue() -> AsyncGenerator[str, None]:
        """Stream data from queue to client.

        If client disconnects, this generator stops but the background
        task continues processing to ensure messages are saved.
        """
        try:
            while True:
                chunk = await queue.get()
                if chunk is None:
                    break
                yield chunk
        except asyncio.CancelledError:
            # Client disconnected (e.g., page refresh)
            # Background task continues running independently
            logger.info(
                "Stream cancelled by client, backend continues processing in background"
            )
            # Don't raise - let the background task complete

    try:
        if request.stream:
            # Start background task BEFORE returning response
            # This ensures processing continues even if client disconnects
            asyncio.create_task(process_in_background())

            return StreamingResponse(
                stream_from_queue(),
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
                images=images_data,
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


def _parse_iso_date(value: Optional[str]) -> Optional[date]:
    if value is None:
        return None
    value = str(value).strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="日期需为 YYYY-MM-DD 格式") from exc


def _infer_default_next_meal() -> tuple[date, str]:
    now = datetime.now()
    if now.hour < 10:
        return now.date(), "lunch"
    if now.hour < 15:
        return now.date(), "dinner"
    if now.hour < 21:
        return now.date(), "snack"
    return now.date() + timedelta(days=1), "breakfast"


MEAL_TYPE_VALUES = {"breakfast", "lunch", "dinner", "snack"}
PLAN_INTENSITY_VALUES = {"conservative", "balanced", "aggressive"}
TRAINING_FOCUS_VALUES = {"low_impact", "strength", "cardio", "mobility"}
PLAN_GOAL_VALUES = {"fat_loss", "muscle_gain", "maintenance", "recovery"}
CUSTOM_SPLIT_PATTERN = re.compile(r"[,，、;\n]+")
PLAN_MODE_TEXT_LIMIT = 200

PLAN_LIBRARY: dict[str, dict[str, list[dict[str, Any]]]] = {
    "fat_loss": {
        "breakfast": [
            {"dish_name": "希腊酸奶莓果燕麦杯", "calories": 340, "description": "高蛋白+高纤维，控饿更稳。"},
            {"dish_name": "番茄鸡蛋全麦卷", "calories": 360, "description": "主食适量，减少上午暴食。"},
            {"dish_name": "豆浆鸡蛋蔬菜碗", "calories": 320, "description": "清爽低负担，准备时间短。"},
        ],
        "lunch": [
            {"dish_name": "清炒虾仁西兰花饭", "calories": 470, "description": "蛋白和蔬菜占比高，油脂可控。"},
            {"dish_name": "鸡胸藜麦时蔬碗", "calories": 450, "description": "稳定能量输出，下午不困乏。"},
            {"dish_name": "豆腐牛肉双拼便当", "calories": 490, "description": "兼顾口味与饱腹，避免补偿性进食。"},
        ],
        "dinner": [
            {"dish_name": "蒸鱼豆腐青菜盘", "calories": 430, "description": "晚餐轻负担，减少夜间波动。"},
            {"dish_name": "番茄鸡胸意面小份", "calories": 460, "description": "控制份量的安抚型主食。"},
            {"dish_name": "菌菇牛肉生菜碗", "calories": 440, "description": "高饱腹低负担，方便批量备餐。"},
        ],
        "snack": [
            {"dish_name": "无糖酸奶坚果小份", "calories": 180, "description": "补充蛋白和健康脂肪。"},
            {"dish_name": "香蕉花生酱半份吐司", "calories": 210, "description": "快速补能，避免晚间冲动加餐。"},
        ],
    },
    "muscle_gain": {
        "breakfast": [
            {"dish_name": "牛奶燕麦蛋白碗", "calories": 430, "description": "提高蛋白与碳水储备。"},
            {"dish_name": "鸡蛋鸡胸全麦三明治", "calories": 460, "description": "训练日前后的稳态早餐。"},
            {"dish_name": "豆乳香蕉花生酱杯", "calories": 420, "description": "补能且易执行。"},
        ],
        "lunch": [
            {"dish_name": "牛肉藜麦能量碗", "calories": 620, "description": "兼顾蛋白与碳水供能。"},
            {"dish_name": "鸡腿饭配时蔬", "calories": 650, "description": "增肌阶段维持足够摄入。"},
            {"dish_name": "三文鱼土豆沙拉", "calories": 610, "description": "优质脂肪辅助恢复。"},
        ],
        "dinner": [
            {"dish_name": "鸡胸意面双蛋白餐", "calories": 580, "description": "晚餐补充恢复所需营养。"},
            {"dish_name": "牛肉豆腐炖菜配饭", "calories": 600, "description": "口味友好，避免增肌期单调。"},
            {"dish_name": "虾仁杂粮饭", "calories": 560, "description": "高蛋白+复合碳水。"},
        ],
        "snack": [
            {"dish_name": "蛋白酸奶水果杯", "calories": 240, "description": "训练后快速补给。"},
            {"dish_name": "牛奶坚果能量棒", "calories": 260, "description": "提高全天总摄入。"},
        ],
    },
    "maintenance": {
        "breakfast": [
            {"dish_name": "全麦三明治配酸奶", "calories": 380, "description": "平衡主食与蛋白。"},
            {"dish_name": "豆浆鸡蛋杂蔬碗", "calories": 360, "description": "简单稳定，适合工作日。"},
            {"dish_name": "燕麦水果坚果杯", "calories": 390, "description": "高纤维，维持饱腹感。"},
        ],
        "lunch": [
            {"dish_name": "鸡腿蔬菜便当", "calories": 520, "description": "口味和营养均衡。"},
            {"dish_name": "豆腐牛肉双拼饭", "calories": 540, "description": "兼顾饱腹与可执行性。"},
            {"dish_name": "虾仁蔬菜荞麦面", "calories": 500, "description": "减少油炸高糖选择。"},
        ],
        "dinner": [
            {"dish_name": "蒸鱼时蔬杂粮饭", "calories": 480, "description": "晚餐不过量，睡眠更稳。"},
            {"dish_name": "鸡胸蘑菇烩饭小份", "calories": 500, "description": "保留满足感，避免报复进食。"},
            {"dish_name": "番茄牛肉蔬菜汤面", "calories": 470, "description": "温和舒适，易坚持。"},
        ],
        "snack": [
            {"dish_name": "酸奶+莓果", "calories": 170, "description": "低负担补给。"},
            {"dish_name": "苹果+奶酪小份", "calories": 190, "description": "维持稳定血糖。"},
        ],
    },
    "recovery": {
        "breakfast": [
            {"dish_name": "温热燕麦牛奶杯", "calories": 360, "description": "温和安抚，减少早晨压力。"},
            {"dish_name": "鸡蛋豆腐粥配青菜", "calories": 340, "description": "消化友好，执行门槛低。"},
            {"dish_name": "酸奶香蕉燕麦杯", "calories": 350, "description": "舒缓型能量补给。"},
        ],
        "lunch": [
            {"dish_name": "番茄鸡胸汤饭", "calories": 480, "description": "暖胃轻负担，情绪期更友好。"},
            {"dish_name": "三文鱼蔬菜碗", "calories": 500, "description": "补充优质脂肪，支持恢复。"},
            {"dish_name": "豆腐牛肉杂蔬煲", "calories": 490, "description": "口味温和，减少内疚感。"},
        ],
        "dinner": [
            {"dish_name": "菌菇鸡汤面小份", "calories": 430, "description": "舒缓型晚餐，避免惩罚性节食。"},
            {"dish_name": "虾仁豆腐蔬菜锅", "calories": 420, "description": "高蛋白且温和。"},
            {"dish_name": "南瓜鸡肉杂粮饭", "calories": 450, "description": "稳定能量，有满足感。"},
        ],
        "snack": [
            {"dish_name": "温牛奶+全麦饼干小份", "calories": 190, "description": "夜间压力时的低负担选择。"},
            {"dish_name": "坚果酸奶杯", "calories": 200, "description": "补充营养且不负担。"},
        ],
    },
}

RELAX_MODE_MAP = {
    "breathing": "3 轮方块呼吸（吸4秒-停4秒-呼4秒-停4秒）。",
    "walk": "餐后慢走 10 分钟，放松肩颈和下颌。",
    "journaling": "用 3 句话记录情绪触发点与可替代行动。",
    "music": "听 10 分钟舒缓音乐，避免持续刷短视频。",
}

TRAINING_FOCUS_MAP = {
    "low_impact": "低冲击恢复训练",
    "strength": "基础力量训练",
    "cardio": "有氧耐力训练",
    "mobility": "灵活性与拉伸训练",
}

INTENSITY_LABEL_MAP = {
    "conservative": "保守",
    "balanced": "平衡",
    "aggressive": "积极",
}

INTENSITY_CALORIE_DELTA = {
    "conservative": 80,
    "balanced": 0,
    "aggressive": -80,
}

INTENSITY_WEEKLY_HINT = {
    "conservative": "下周以稳态恢复为主，优先降低波动。",
    "balanced": "下周保持稳态推进，兼顾执行感和灵活度。",
    "aggressive": "下周以积极纠偏为主，请注意恢复与睡眠。",
}


def _normalize_text(value: Any, max_length: int = PLAN_MODE_TEXT_LIMIT) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) > max_length:
        return text[:max_length]
    return text


def _normalize_text_list(
    value: Any,
    *,
    max_items: int = 8,
    item_max_length: int = 40,
) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = _normalize_text(item, max_length=item_max_length)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
        if len(result) >= max_items:
            break
    return result


def _split_custom_text(value: Any, *, item_max_length: int = 40) -> list[str]:
    text = _normalize_text(value, max_length=PLAN_MODE_TEXT_LIMIT)
    if not text:
        return []
    items = [part.strip() for part in CUSTOM_SPLIT_PATTERN.split(text) if part.strip()]
    dedup: list[str] = []
    seen: set[str] = set()
    for item in items:
        normalized = _normalize_text(item, max_length=item_max_length)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        dedup.append(normalized)
    return dedup


def _clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))


def _get_week_start(target_date: date) -> date:
    return target_date - timedelta(days=target_date.weekday())


def _build_plan_profile(action_data: dict[str, Any]) -> dict[str, Any]:
    goal = str(action_data.get("goal") or "fat_loss").strip().lower()
    if goal not in PLAN_GOAL_VALUES:
        goal = "fat_loss"

    weekly_intensity = str(action_data.get("weekly_intensity") or "balanced").strip().lower()
    if weekly_intensity not in PLAN_INTENSITY_VALUES:
        weekly_intensity = "balanced"

    training_focus = str(action_data.get("training_focus") or "low_impact").strip().lower()
    if training_focus not in TRAINING_FOCUS_VALUES:
        training_focus = "low_impact"

    food_types = _normalize_text_list(action_data.get("food_types"))
    restrictions = _normalize_text_list(action_data.get("restrictions"))
    allergies = _normalize_text_list(action_data.get("allergies"))
    relax_modes = _normalize_text_list(action_data.get("relax_modes"))
    food_types.extend(_split_custom_text(action_data.get("food_type_custom")))
    restrictions.extend(_split_custom_text(action_data.get("restriction_custom")))
    allergies.extend(_split_custom_text(action_data.get("allergy_custom")))
    relax_modes.extend(_split_custom_text(action_data.get("relax_custom")))

    return {
        "goal": goal,
        "food_types": _normalize_text_list(food_types),
        "restrictions": _normalize_text_list(restrictions),
        "allergies": _normalize_text_list(allergies),
        "relax_modes": _normalize_text_list(relax_modes),
        "weekly_intensity": weekly_intensity,
        "training_focus": training_focus,
        "training_minutes_per_day": _clamp_int(
            action_data.get("training_minutes_per_day"),
            default=25,
            minimum=10,
            maximum=120,
        ),
        "training_days_per_week": _clamp_int(
            action_data.get("training_days_per_week"),
            default=3,
            minimum=1,
            maximum=7,
        ),
        "cook_time_minutes": _clamp_int(
            action_data.get("cook_time_minutes"),
            default=30,
            minimum=10,
            maximum=180,
        ),
        "special_days": _normalize_text(action_data.get("special_days")),
        "training_custom": _normalize_text(action_data.get("training_custom")),
    }


def _build_relax_suggestions(relax_modes: list[str]) -> list[str]:
    suggestions: list[str] = []
    for mode in relax_modes:
        hint = RELAX_MODE_MAP.get(mode)
        if hint and hint not in suggestions:
            suggestions.append(hint)
    if not suggestions:
        suggestions.extend(
            [
                RELAX_MODE_MAP["breathing"],
                RELAX_MODE_MAP["walk"],
            ]
        )
    return suggestions[:3]


def _build_training_plan(
    *,
    week_start: date,
    weekly_intensity: str,
    training_focus: str,
    training_minutes_per_day: int,
    training_days_per_week: int,
    training_custom: str,
) -> list[dict[str, Any]]:
    focus_label = TRAINING_FOCUS_MAP.get(training_focus, TRAINING_FOCUS_MAP["low_impact"])
    rest_hint = "主动恢复（散步+拉伸）"
    days: list[dict[str, Any]] = []
    for day_index in range(7):
        target_date = week_start + timedelta(days=day_index)
        if day_index < training_days_per_week:
            title = f"{focus_label} Day {day_index + 1}"
            description = f"{training_minutes_per_day} 分钟，强度档：{INTENSITY_LABEL_MAP.get(weekly_intensity, '平衡')}"
            if training_custom:
                description = f"{description}；个性化备注：{training_custom}"
        else:
            title = "恢复日"
            description = rest_hint
        days.append(
            {
                "date": target_date.isoformat(),
                "title": title,
                "description": description,
            }
        )
    return days


def _adjust_calories(base_calories: int, weekly_intensity: str) -> int:
    delta = INTENSITY_CALORIE_DELTA.get(weekly_intensity, 0)
    return max(120, base_calories + delta)


def _build_meal_candidates(
    *,
    goal: str,
    meal_type: str,
    day_index: int,
    weekly_intensity: str,
    limit: int = 3,
) -> list[dict[str, Any]]:
    # AUTO macro estimation: deterministic fallback to ensure plan meals always
    # carry P/F/C even when RAG is unavailable or not triggered.
    from app.diet.macro_estimation import estimate_macros_from_calories

    goal_library = PLAN_LIBRARY.get(goal) or PLAN_LIBRARY["fat_loss"]
    meal_options = goal_library.get(meal_type) or PLAN_LIBRARY["maintenance"][meal_type]
    max_candidates = max(1, min(limit, len(meal_options)))
    candidates: list[dict[str, Any]] = []
    for offset in range(max_candidates):
        template = meal_options[(day_index + offset) % len(meal_options)]
        calories = _adjust_calories(int(template.get("calories") or 420), weekly_intensity)
        macros = estimate_macros_from_calories(calories, goal)
        candidates.append(
            {
                "dish_name": str(template.get("dish_name") or "个性化推荐餐"),
                "calories": calories,
                "protein": macros.get("protein_g"),
                "fat": macros.get("fat_g"),
                "carbs": macros.get("carbs_g"),
                "nutrition_source": macros.get("source"),
                "nutrition_confidence": macros.get("confidence"),
                "description": template.get("description") or "",
            }
        )
    return candidates


def _build_week_plan_preview(profile: dict[str, Any]) -> dict[str, Any]:
    today = date.today()
    week_start = _get_week_start(today)
    goal = str(profile.get("goal") or "fat_loss")
    weekly_intensity = str(profile.get("weekly_intensity") or "balanced")
    relax_modes = profile.get("relax_modes") if isinstance(profile.get("relax_modes"), list) else []

    preview_days: list[dict[str, Any]] = []
    planned_meals: list[dict[str, Any]] = []

    for day_index in range(7):
        target_date = week_start + timedelta(days=day_index)
        meal_blocks: list[dict[str, Any]] = []
        for meal_type in ("breakfast", "lunch", "dinner"):
            candidates = _build_meal_candidates(
                goal=goal,
                meal_type=meal_type,
                day_index=day_index,
                weekly_intensity=weekly_intensity,
            )
            default_candidate = candidates[0]
            dishes = [
                {
                    "name": default_candidate["dish_name"],
                    "calories": default_candidate["calories"],
                    "protein": default_candidate.get("protein"),
                    "fat": default_candidate.get("fat"),
                    "carbs": default_candidate.get("carbs"),
                    "nutrition_source": default_candidate.get("nutrition_source"),
                    "nutrition_confidence": default_candidate.get(
                        "nutrition_confidence"
                    ),
                }
            ]
            meal_blocks.append(
                {
                    "meal_type": meal_type,
                    "dish_name": dishes[0]["name"],
                    "calories": default_candidate["calories"],
                    "description": default_candidate.get("description") or "",
                    "candidates": candidates,
                }
            )
            planned_meals.append(
                {
                    "plan_date": target_date.isoformat(),
                    "meal_type": meal_type,
                    "dishes": dishes,
                    "notes": "由 PlanMode 个性化推荐卡生成",
                }
            )
        preview_days.append(
            {
                "date": target_date.isoformat(),
                "weekday": target_date.strftime("%A"),
                "meals": meal_blocks,
            }
        )

    training_plan = _build_training_plan(
        week_start=week_start,
        weekly_intensity=weekly_intensity,
        training_focus=str(profile.get("training_focus") or "low_impact"),
        training_minutes_per_day=int(profile.get("training_minutes_per_day") or 25),
        training_days_per_week=int(profile.get("training_days_per_week") or 3),
        training_custom=_normalize_text(profile.get("training_custom")),
    )

    return {
        "week_start_date": week_start.isoformat(),
        "weekly_intensity": weekly_intensity,
        "weekly_intensity_label": INTENSITY_LABEL_MAP.get(weekly_intensity, "平衡"),
        "weekly_hint": INTENSITY_WEEKLY_HINT.get(
            weekly_intensity,
            INTENSITY_WEEKLY_HINT["balanced"],
        ),
        "preview_days": preview_days,
        "planned_meals": planned_meals,
        "relax_suggestions": _build_relax_suggestions(relax_modes),
        "training_plan": training_plan,
    }


async def _try_generate_plan_llm_supplement(profile: dict[str, Any]) -> Optional[str]:
    try:
        from app.config import settings as app_settings
        from app.llm.provider import LLMProvider
        from langchain_core.messages import HumanMessage, SystemMessage
    except Exception:
        return None

    prompt = (
        "请基于以下用户偏好，给出 1~2 句温和且可执行的周计划提醒，"
        "不要输出列表：\n"
        f"目标={profile.get('goal')}; "
        f"强度={profile.get('weekly_intensity')}; "
        f"食物类型={','.join(profile.get('food_types') or [])}; "
        f"限制={','.join(profile.get('restrictions') or [])}; "
        f"训练偏好={profile.get('training_focus')}"
    )
    try:
        provider = LLMProvider(app_settings.llm)
        invoker = provider.create_invoker("fast", temperature=0.3, streaming=False)
        response = await asyncio.wait_for(
            invoker.ainvoke(
                [
                    SystemMessage(
                        content="你是饮食与训练教练，请输出简短且鼓励性的中文建议。"
                    ),
                    HumanMessage(content=prompt),
                ]
            ),
            timeout=6.0,
        )
        content = getattr(response, "content", "")
        text = _normalize_text(content, max_length=180)
        return text or None
    except Exception:
        return None


async def _persist_planmode_profile(
    *,
    user_id: str,
    profile: dict[str, Any],
) -> dict[str, Any]:
    common_foods = _normalize_text_list(profile.get("food_types"))
    avoided_foods = _normalize_text_list(profile.get("restrictions"))

    diet_tags = _normalize_text_list(
        [
            profile.get("goal"),
            f"intensity:{profile.get('weekly_intensity')}",
            f"training:{profile.get('training_focus')}",
            *(_normalize_text_list(profile.get("relax_modes"), max_items=3)),
        ],
        max_items=8,
        item_max_length=50,
    )

    planmode_profile = {
        "goal": profile.get("goal"),
        "allergies": _normalize_text_list(profile.get("allergies")),
        "relax_modes": _normalize_text_list(profile.get("relax_modes")),
        "weekly_intensity": profile.get("weekly_intensity"),
        "training_focus": profile.get("training_focus"),
        "training_minutes_per_day": profile.get("training_minutes_per_day"),
        "training_days_per_week": profile.get("training_days_per_week"),
        "cook_time_minutes": profile.get("cook_time_minutes"),
        "special_days": _normalize_text(profile.get("special_days")),
        "training_custom": _normalize_text(profile.get("training_custom")),
        "updated_at": datetime.utcnow().isoformat(),
    }

    return await diet_service.update_user_preference(
        user_id,
        common_foods=common_foods,
        avoided_foods=avoided_foods,
        diet_tags=diet_tags,
        stats={"planmode_profile": planmode_profile},
    )


async def _upsert_week_plan_meals(
    *,
    user_id: str,
    planned_meals: list[dict[str, Any]],
) -> dict[str, Any]:
    if not planned_meals:
        raise HTTPException(status_code=400, detail="planned_meals 不能为空")

    cache_by_week: dict[str, dict[tuple[str, str], dict[str, Any]]] = {}
    created_count = 0
    updated_count = 0
    applied_meals: list[dict[str, Any]] = []

    for item in planned_meals:
        if not isinstance(item, dict):
            continue
        plan_date = _parse_iso_date(item.get("plan_date"))
        meal_type = str(item.get("meal_type") or "").strip().lower()
        if not plan_date or meal_type not in MEAL_TYPE_VALUES:
            continue
        raw_dishes = item.get("dishes")
        dishes = raw_dishes if isinstance(raw_dishes, list) else []
        sanitized_dishes: list[dict[str, Any]] = []
        for dish in dishes:
            if not isinstance(dish, dict):
                continue
            name = _normalize_text(dish.get("name"), max_length=80)
            if not name:
                continue
            calories = dish.get("calories")
            try:
                calories_value = int(calories) if calories is not None else None
            except (TypeError, ValueError):
                calories_value = None
            sanitized_dishes.append(
                {
                    "name": name,
                    "calories": calories_value,
                    "protein": dish.get("protein"),
                    "fat": dish.get("fat"),
                    "carbs": dish.get("carbs"),
                    "weight_g": dish.get("weight_g"),
                    "unit": dish.get("unit"),
                }
            )
        if not sanitized_dishes:
            continue

        week_start = _get_week_start(plan_date).isoformat()
        if week_start not in cache_by_week:
            plan = await diet_service.get_plan_by_week(user_id, _get_week_start(plan_date))
            existing_map: dict[tuple[str, str], dict[str, Any]] = {}
            if plan and isinstance(plan.get("meals"), list):
                for meal in plan["meals"]:
                    if not isinstance(meal, dict):
                        continue
                    key = (
                        str(meal.get("plan_date") or ""),
                        str(meal.get("meal_type") or "").lower(),
                    )
                    existing_map[key] = meal
            cache_by_week[week_start] = existing_map

        existing_map = cache_by_week[week_start]
        key = (plan_date.isoformat(), meal_type)
        notes = _normalize_text(item.get("notes")) or "由 PlanMode 个性化推荐卡写入"
        existing = existing_map.get(key)
        if existing and existing.get("id"):
            updated = await diet_service.update_meal(
                meal_id=str(existing.get("id")),
                user_id=user_id,
                plan_date=plan_date,
                meal_type=meal_type,
                dishes=sanitized_dishes,
                notes=notes,
            )
            if updated:
                existing_map[key] = updated
                applied_meals.append(updated)
                updated_count += 1
            continue

        created = await diet_service.add_meal(
            user_id=user_id,
            plan_date=plan_date,
            meal_type=meal_type,
            dishes=sanitized_dishes,
            notes=notes,
        )
        if created:
            existing_map[key] = created
            applied_meals.append(created)
            created_count += 1

    if not applied_meals:
        raise HTTPException(status_code=400, detail="未找到可写入的计划餐次")

    return {
        "created_count": created_count,
        "updated_count": updated_count,
        "total_applied": len(applied_meals),
        "meals": applied_meals,
    }


def _build_weekly_progress_summary(
    *,
    weekly_summary: dict[str, Any],
    deviation: dict[str, Any],
    intensity_level: str,
) -> str:
    analysis = deviation.get("analysis") if isinstance(deviation, dict) else {}
    if not isinstance(analysis, dict):
        analysis = {}
    execution_rate = analysis.get("execution_rate")
    total_deviation = analysis.get("total_deviation")
    avg_daily = weekly_summary.get("avg_daily_calories") if isinstance(weekly_summary, dict) else None
    try:
        execution_rate_value = float(execution_rate) if execution_rate is not None else None
    except (TypeError, ValueError):
        execution_rate_value = None
    try:
        total_deviation_value = int(total_deviation) if total_deviation is not None else None
    except (TypeError, ValueError):
        total_deviation_value = None
    try:
        avg_daily_value = float(avg_daily) if avg_daily is not None else None
    except (TypeError, ValueError):
        avg_daily_value = None
    intensity_label = INTENSITY_LABEL_MAP.get(intensity_level, "平衡")
    base = f"当前为 {intensity_label} 强度。"
    if execution_rate_value is not None and total_deviation_value is not None:
        return (
            f"{base} 本周执行率约 {execution_rate_value:.1f}% ，总偏差 {total_deviation_value} kcal。"
        )
    if avg_daily_value is not None:
        return f"{base} 本周日均摄入约 {avg_daily_value:.0f} kcal。"
    return f"{base} 已完成周进度分析。"


def _parse_iso_datetime(value: Any) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    raw = raw.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


async def _load_emotion_demo_state(session_id: str) -> dict[str, Any]:
    try:
        metadata = await agent_service.repository.get_session_metadata(session_id)
    except Exception as exc:
        logger.warning("Failed to read session metadata %s: %s", session_id, exc)
        return {}

    state = metadata.get(EMOTION_DEMO_METADATA_KEY)
    if isinstance(state, dict):
        return dict(state)
    return {}


async def _save_emotion_demo_state(session_id: str, state: dict[str, Any]) -> None:
    if not isinstance(state, dict):
        return
    try:
        await agent_service.repository.merge_session_metadata(
            session_id,
            {EMOTION_DEMO_METADATA_KEY: state},
        )
    except Exception as exc:
        logger.warning("Failed to persist session metadata %s: %s", session_id, exc)


def _should_emit_emotion_followup(action_id: str, state: dict[str, Any]) -> bool:
    last_action = str(state.get("last_followup_for_action_id") or "").strip()
    if last_action and last_action == action_id:
        return False

    last_followup_at = _parse_iso_datetime(state.get("last_followup_at"))
    if not last_followup_at:
        return True

    now = (
        datetime.now(last_followup_at.tzinfo)
        if last_followup_at.tzinfo
        else datetime.utcnow()
    )
    return (
        now - last_followup_at
    ).total_seconds() >= EMOTION_FOLLOW_UP_COOLDOWN_SECONDS


def _build_emotion_followup_smart_action(
    *,
    session_id: str,
    parent_action_id: str,
    emotion_level: Optional[str],
    used_provider: str,
    effective_goal: Optional[int],
    applied_delta: Optional[int],
    capped: bool,
) -> dict[str, Any]:
    plan_date, meal_type = _infer_default_next_meal()
    emotion_label_map = {
        "low": "轻度波动",
        "medium": "中度压力",
        "high": "高压时段",
    }
    emotion_label = emotion_label_map.get(
        str(emotion_level or "").strip().lower(),
        "情绪波动",
    )
    provider_label = "MCP" if used_provider == "mcp" else "本地工具"
    capped_hint = "（已触发上限保护）" if capped else ""
    applied_hint = (
        f"本次已弹性调整 +{applied_delta} kcal{capped_hint}"
        if isinstance(applied_delta, int)
        else "已完成预算弹性调整"
    )
    goal_hint = (
        f"，当前有效预算约 {effective_goal} kcal"
        if isinstance(effective_goal, int)
        else ""
    )

    return {
        "action_id": f"smart-recommendation-{uuid.uuid4().hex}",
        "action_type": "smart_recommendation_card",
        "title": "下一步我建议你这样稳住节奏",
        "description": (
            f"已识别为{emotion_label}；{applied_hint}{goal_hint}。"
            f"下面这张卡可以直接执行（预算来源：{provider_label}）。"
        ),
        "timeout_seconds": 10,
        "timeout_mode": "timeout_suggest_only",
        "default_timeout_suggestion": "超时后保留建议，不会自动写入饮食数据。",
        "next_meal_options": [
            {
                "option_id": "stabilize",
                "title": "稳态轻负担餐",
                "description": "优先蛋白 + 蔬菜，避免补偿性节食和二次暴食。",
                "meal_type": meal_type,
                "plan_date": plan_date.isoformat(),
                "dish_name": "鸡蛋豆腐蔬菜碗",
                "calories": 420,
                "protein": 28.0,
                "fat": 14.0,
                "carbs": 36.0,
            },
            {
                "option_id": "protein",
                "title": "高蛋白稳定餐",
                "description": "提高饱腹感，减少情绪波动带来的冲动进食。",
                "meal_type": meal_type,
                "plan_date": plan_date.isoformat(),
                "dish_name": "鸡胸肉沙拉配酸奶",
                "calories": 460,
                "protein": 34.0,
                "fat": 16.0,
                "carbs": 32.0,
            },
            {
                "option_id": "comfort",
                "title": "温和安抚餐",
                "description": "保留满足感，不用通过惩罚来“补偿”自己。",
                "meal_type": meal_type,
                "plan_date": plan_date.isoformat(),
                "dish_name": "燕麦酸奶水果杯",
                "calories": 380,
                "protein": 16.0,
                "fat": 10.0,
                "carbs": 52.0,
            },
        ],
        "relax_suggestions": _build_relax_suggestions(["breathing", "walk", "journaling"]),
        "weekly_progress": {
            "trigger_hint": "看本周进度",
            "summary_text": "点击查看本周执行偏差，做一次轻量复盘。",
            "execution_rate": None,
            "total_deviation": None,
        },
        "budget_options": [50, 100, 150],
        "source": "emotion_support_followup",
        "session_id": session_id,
        "parent_action_id": parent_action_id,
    }


@router.post(
    "/agent/smart-actions/apply",
    response_model=ApplySmartActionResponse,
)
async def apply_smart_action(
    payload: ApplySmartActionRequest,
    http_request: Request,
) -> ApplySmartActionResponse:
    """Apply action from smart recommendation card."""
    user_id = getattr(http_request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="需要登录")

    session = await agent_service.get_session(payload.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.get("user_id") != str(user_id):
        raise HTTPException(status_code=403, detail="无权访问此会话")

    action_payload = await _find_smart_ui_action(payload.session_id, payload.action_id)
    if not action_payload:
        raise HTTPException(status_code=404, detail="未知或已过期的 action_id")
    action_type = str(action_payload.get("action_type") or "")
    if payload.action_kind in {"submit_plan_profile", "apply_week_plan"}:
        if action_type not in {"meal_plan_planmode_card", "meal_plan_preview_card"}:
            raise HTTPException(status_code=400, detail="该 action_id 不支持 PlanMode 提交")

    existing = await _find_existing_smart_action_result(
        payload.session_id,
        payload.action_id,
        payload.action_kind,
    )
    if existing:
        return ApplySmartActionResponse(
            action_id=payload.action_id,
            action_kind=payload.action_kind,
            mode=str(existing.get("mode") or payload.mode),
            applied=bool(existing.get("applied")),
            used_provider=str(existing.get("used_provider") or "local"),
            message=str(existing.get("message") or "操作已执行"),
            result=existing.get("result")
            if isinstance(existing.get("result"), dict)
            else None,
        )

    if payload.mode == "timeout_suggest_only":
        response_data = {
            "action_id": payload.action_id,
            "action_kind": payload.action_kind,
            "mode": payload.mode,
            "applied": False,
            "used_provider": "none",
            "message": "仅生成建议，不自动写入饮食数据。",
            "result": {
                "suggestion_only": True,
            },
        }
    else:
        action_data = payload.payload or {}
        if not isinstance(action_data, dict):
            raise HTTPException(status_code=400, detail="payload 必须是对象")

        if payload.action_kind == "submit_plan_profile":
            profile = _build_plan_profile(action_data)
            preference = await _persist_planmode_profile(
                user_id=str(user_id),
                profile=profile,
            )
            preview = _build_week_plan_preview(profile)
            llm_supplement = await _try_generate_plan_llm_supplement(profile)
            used_provider = "template+llm" if llm_supplement else "template"
            preview_action = {
                "action_id": payload.action_id,
                "action_type": "meal_plan_preview_card",
                "title": "你的个性化周计划预览已生成",
                "description": "可先查看再确认写入；若不确认，本次不会自动写库。",
                "weekly_intensity": preview["weekly_intensity"],
                "weekly_intensity_label": preview["weekly_intensity_label"],
                "weekly_hint": preview["weekly_hint"],
                "preview_days": preview["preview_days"],
                "planned_meals": preview["planned_meals"],
                "relax_suggestions": preview["relax_suggestions"],
                "training_plan": preview["training_plan"],
                "llm_supplement": llm_supplement,
                "source": "planmode_pipeline",
                "session_id": payload.session_id,
            }
            response_data = {
                "action_id": payload.action_id,
                "action_kind": payload.action_kind,
                "mode": payload.mode,
                "applied": False,
                "used_provider": used_provider,
                "message": "偏好已保存，已生成个性化周计划预览。",
                "result": {
                    "profile_saved": True,
                    "preference": preference,
                    "preview_action": preview_action,
                    "week_start_date": preview["week_start_date"],
                },
            }
        elif payload.action_kind == "apply_week_plan":
            planned_meals_raw = action_data.get("planned_meals")
            if not isinstance(planned_meals_raw, list):
                raise HTTPException(status_code=400, detail="planned_meals 必须为数组")
            plan_apply_result = await _upsert_week_plan_meals(
                user_id=str(user_id),
                planned_meals=[item for item in planned_meals_raw if isinstance(item, dict)],
            )
            response_data = {
                "action_id": payload.action_id,
                "action_kind": payload.action_kind,
                "mode": payload.mode,
                "applied": True,
                "used_provider": "local",
                "message": (
                    f"已同步本周计划：新增 {plan_apply_result['created_count']} 条，"
                    f"更新 {plan_apply_result['updated_count']} 条。"
                ),
                "result": plan_apply_result,
            }
        elif payload.action_kind == "apply_budget_adjust":
            delta_raw = action_data.get("delta_calories", 100)
            try:
                delta_calories = int(delta_raw)
            except (TypeError, ValueError) as exc:
                raise HTTPException(status_code=400, detail="delta_calories 必须为整数") from exc
            if delta_calories not in {50, 100, 150}:
                raise HTTPException(status_code=400, detail="delta_calories 仅支持 50/100/150")

            try:
                result = await emotion_budget_service.adjust_today_budget(
                    user_id=str(user_id),
                    delta_calories=delta_calories,
                    reason=payload.reason or "智能推荐卡预算调整",
                    mode="user_select",
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            except RuntimeError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc

            response_data = {
                "action_id": payload.action_id,
                "action_kind": payload.action_kind,
                "mode": payload.mode,
                "applied": bool(result.get("applied")),
                "used_provider": result.get("used_provider") or "unknown",
                "message": result.get("message") or "预算调整完成",
                "result": {
                    "requested": delta_calories,
                    "applied": result.get("applied"),
                    "capped": bool(result.get("capped")),
                    "effective_goal": result.get("effective_goal"),
                    "goal_source": result.get("goal_source"),
                    "goal_seeded": result.get("goal_seeded"),
                },
            }
        elif payload.action_kind == "apply_next_meal_plan":
            plan_date = _parse_iso_date(action_data.get("plan_date"))
            meal_type = str(action_data.get("meal_type") or "").strip().lower()
            if not plan_date or meal_type not in {"breakfast", "lunch", "dinner", "snack"}:
                inferred_date, inferred_meal = _infer_default_next_meal()
                if not plan_date:
                    plan_date = inferred_date
                if meal_type not in {"breakfast", "lunch", "dinner", "snack"}:
                    meal_type = inferred_meal

            dish_name = str(action_data.get("dish_name") or "").strip() or "智能推荐轻负担餐"
            calories = action_data.get("calories")
            protein = action_data.get("protein")
            fat = action_data.get("fat")
            carbs = action_data.get("carbs")
            try:
                calories_value = int(calories) if calories is not None else None
            except (TypeError, ValueError) as exc:
                raise HTTPException(status_code=400, detail="calories 必须为整数") from exc

            try:
                protein_value = float(protein) if protein is not None else None
                fat_value = float(fat) if fat is not None else None
                carbs_value = float(carbs) if carbs is not None else None
            except (TypeError, ValueError) as exc:
                raise HTTPException(
                    status_code=400,
                    detail="protein/fat/carbs 必须为数字",
                ) from exc

            dishes = [
                {
                    "name": dish_name,
                    "calories": calories_value,
                    "protein": protein_value,
                    "fat": fat_value,
                    "carbs": carbs_value,
                }
            ]
            meal = await diet_service.add_meal(
                user_id=str(user_id),
                plan_date=plan_date,
                meal_type=meal_type,
                dishes=dishes,
                notes="来自智能推荐卡的一键纠偏建议",
            )

            response_data = {
                "action_id": payload.action_id,
                "action_kind": payload.action_kind,
                "mode": payload.mode,
                "applied": True,
                "used_provider": "local",
                "message": "已写入计划餐次，可在饮食管理中查看",
                "result": {
                    "plan_date": plan_date.isoformat(),
                    "meal_type": meal_type,
                    "meal": meal,
                },
            }
        elif payload.action_kind == "fetch_weekly_progress":
            week_start = _parse_iso_date(action_data.get("week_start_date"))
            if not week_start:
                today = date.today()
                week_start = today - timedelta(days=today.weekday())
            intensity_level = str(action_data.get("intensity_level") or "balanced").strip().lower()
            if intensity_level not in PLAN_INTENSITY_VALUES:
                intensity_level = "balanced"

            weekly_summary = await diet_service.get_weekly_summary(
                str(user_id),
                week_start,
            )
            deviation = await diet_service.get_deviation_analysis(
                str(user_id),
                week_start,
            )
            summary_text = _build_weekly_progress_summary(
                weekly_summary=weekly_summary,
                deviation=deviation,
                intensity_level=intensity_level,
            )
            response_data = {
                "action_id": payload.action_id,
                "action_kind": payload.action_kind,
                "mode": payload.mode,
                "applied": False,
                "used_provider": "local",
                "message": summary_text,
                "result": {
                    "weekly_summary": weekly_summary,
                    "deviation": deviation,
                    "intensity_level": intensity_level,
                    "summary_text": summary_text,
                },
            }
        else:
            raise HTTPException(status_code=400, detail="未知 action_kind")

    trace_subagent_name = (
        "diet_planner"
        if payload.action_kind in {"submit_plan_profile", "apply_week_plan"}
        else "emotion_support"
    )
    trace_step = {
        "iteration": 0,
        "action": "smart_action_result",
        "content": response_data,
        "error": None,
        "source": "subagent",
        "subagent_name": trace_subagent_name,
    }
    trace_steps = []
    if payload.action_kind == "submit_plan_profile":
        result_payload = response_data.get("result")
        if isinstance(result_payload, dict):
            preview_action = result_payload.get("preview_action")
            if isinstance(preview_action, dict):
                trace_steps.append(
                    {
                        "iteration": 0,
                        "action": "ui_action",
                        "content": preview_action,
                        "error": None,
                        "source": "subagent",
                        "subagent_name": trace_subagent_name,
                    }
                )
    trace_steps.append(trace_step)
    await agent_service.repository.save_message(
        payload.session_id,
        "assistant",
        response_data["message"],
        trace=trace_steps,
    )

    return ApplySmartActionResponse(**response_data)


@router.post(
    "/agent/emotion-actions/apply-budget-adjust",
    response_model=ApplyEmotionBudgetAdjustResponse,
)
async def apply_emotion_budget_adjust(
    payload: ApplyEmotionBudgetAdjustRequest,
    http_request: Request,
) -> ApplyEmotionBudgetAdjustResponse:
    """Apply emotion-support budget adjustment from chat card."""
    user_id = getattr(http_request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="需要登录")

    session = await agent_service.get_session(payload.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.get("user_id") != str(user_id):
        raise HTTPException(status_code=403, detail="无权访问此会话")

    action_payload = await _find_emotion_ui_action(payload.session_id, payload.action_id)
    if not action_payload:
        raise HTTPException(status_code=404, detail="未知或已过期的 action_id")

    if not action_payload.get("can_apply", True):
        reason = action_payload.get("unavailable_reason") or "当前自动预算调整不可用"
        raise HTTPException(status_code=400, detail=reason)

    existing = await _find_existing_emotion_action_result(
        payload.session_id,
        payload.action_id,
    )
    if existing:
        return ApplyEmotionBudgetAdjustResponse(
            action_id=payload.action_id,
            requested=int(existing.get("requested") or payload.delta_calories),
            applied=existing.get("applied"),
            capped=bool(existing.get("capped")),
            effective_goal=existing.get("effective_goal"),
            goal_source=existing.get("goal_source"),
            goal_seeded=existing.get("goal_seeded"),
            used_provider=str(existing.get("used_provider") or "unknown"),
            mode=str(existing.get("mode") or payload.mode),
            message=str(existing.get("message") or "调整已完成"),
        )

    demo_state = await _load_emotion_demo_state(payload.session_id)
    should_emit_followup = _should_emit_emotion_followup(payload.action_id, demo_state)

    try:
        result = await emotion_budget_service.adjust_today_budget(
            user_id=str(user_id),
            delta_calories=payload.delta_calories,
            reason=payload.reason or "情绪安抚自动预算调整",
            mode=payload.mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    response_data = {
        "action_id": payload.action_id,
        "requested": payload.delta_calories,
        "applied": result.get("applied"),
        "capped": bool(result.get("capped")),
        "effective_goal": result.get("effective_goal"),
        "goal_source": result.get("goal_source"),
        "goal_seeded": result.get("goal_seeded"),
        "used_provider": result.get("used_provider") or "unknown",
        "mode": payload.mode,
        "message": result.get("message") or "自动调整完成",
    }

    applied = response_data["applied"]
    applied_text = f"+{applied}" if isinstance(applied, int) else "已应用"
    capped_text = "（已触发上限保护）" if response_data["capped"] else ""
    content = (
        f"已同步今日预算调整：请求 +{payload.delta_calories} kcal，"
        f"实际 {applied_text} kcal，当前有效预算 {response_data['effective_goal']} kcal{capped_text}。"
    )
    trace_step = {
        "iteration": 0,
        "action": "emotion_budget_adjust_result",
        "content": response_data,
        "error": None,
        "source": "subagent",
        "subagent_name": "emotion_support",
    }
    trace_steps = [trace_step]

    followup_action: Optional[dict[str, Any]] = None
    if should_emit_followup:
        followup_action = _build_emotion_followup_smart_action(
            session_id=payload.session_id,
            parent_action_id=payload.action_id,
            emotion_level=action_payload.get("emotion_level"),
            used_provider=str(response_data["used_provider"]),
            effective_goal=response_data.get("effective_goal"),
            applied_delta=applied if isinstance(applied, int) else None,
            capped=bool(response_data["capped"]),
        )
        trace_steps.append(
            {
                "iteration": 0,
                "action": "ui_action",
                "content": followup_action,
                "error": None,
                "source": "subagent",
                "subagent_name": "emotion_support",
            }
        )

    now_iso = datetime.utcnow().isoformat()
    updated_state = dict(demo_state)
    updated_state.update(
        {
            "last_emotion_level": action_payload.get("emotion_level"),
            "last_budget_provider": response_data["used_provider"],
            "last_budget_action_id": payload.action_id,
            "last_budget_applied_at": now_iso,
        }
    )
    if followup_action:
        updated_state.update(
            {
                "last_followup_for_action_id": payload.action_id,
                "last_followup_action_id": followup_action.get("action_id"),
                "last_followup_at": now_iso,
            }
        )
    await _save_emotion_demo_state(payload.session_id, updated_state)

    await agent_service.repository.save_message(
        payload.session_id,
        "assistant",
        content,
        trace=trace_steps,
    )

    return ApplyEmotionBudgetAdjustResponse(**response_data)


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


# ==================== Subagent API Endpoints ====================


class SubagentSchema(BaseModel):
    """Subagent schema for API responses."""

    name: str
    display_name: str
    description: str
    system_prompt: str
    tools: List[str]
    max_iterations: int
    enabled: bool
    builtin: bool
    category: str


class SubagentListResponse(BaseModel):
    """Response model for subagent list."""

    subagents: List[SubagentSchema]


class SubagentToggleRequest(BaseModel):
    """Request model for enabling/disabling a subagent."""

    enabled: bool


class CreateSubagentRequest(BaseModel):
    """Request model for creating a custom subagent."""

    name: str = Field(..., min_length=2, max_length=64, pattern=r"^[a-z0-9_]+$")
    display_name: str = Field(..., min_length=1, max_length=64)
    description: str = Field(..., min_length=10, max_length=500)
    system_prompt: str = Field(..., min_length=20, max_length=10000)
    tools: List[str] = Field(default_factory=list)
    max_iterations: int = Field(default=10, ge=1, le=50)
    category: str = Field(default="custom", max_length=32)


class UpdateSubagentRequest(BaseModel):
    """Request model for updating a custom subagent."""

    display_name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    description: Optional[str] = Field(default=None, min_length=10, max_length=500)
    system_prompt: Optional[str] = Field(default=None, min_length=20, max_length=10000)
    tools: Optional[List[str]] = None
    max_iterations: Optional[int] = Field(default=None, ge=1, le=50)
    category: Optional[str] = Field(default=None, max_length=32)


@router.get("/agent/subagents")
async def list_subagents(http_request: Request) -> SubagentListResponse:
    """
    List all available subagents for the current user.

    Returns both builtin and user-defined subagents with their enabled status.

    **Response:**
    ```json
    {
        "subagents": [
            {
                "name": "diet_planner",
                "display_name": "饮食规划专家",
                "description": "专业的饮食规划助手...",
                "tools": ["datetime", "web_search", "diet_analysis"],
                "max_iterations": 15,
                "enabled": true,
                "builtin": true,
                "category": "diet"
            }
        ]
    }
    ```
    """
    user_id = getattr(http_request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="需要登录")

    configs = await subagent_service.sync_user_subagents(user_id)

    subagents = [
        SubagentSchema(
            name=config.name,
            display_name=config.display_name,
            description=config.description,
            system_prompt=config.system_prompt,
            tools=config.tools,
            max_iterations=config.max_iterations,
            enabled=config.enabled,
            builtin=config.builtin,
            category=config.category,
        )
        for config in configs
    ]

    return SubagentListResponse(subagents=subagents)


@router.patch("/agent/subagents/{subagent_name}")
async def toggle_subagent(
    subagent_name: str,
    request: SubagentToggleRequest,
    http_request: Request,
):
    """
    Enable or disable a subagent for the current user.

    **Parameters:**
    - `subagent_name`: The name of the subagent to toggle

    **Request Body:**
    - `enabled`: Whether to enable (true) or disable (false) the subagent
    """
    user_id = getattr(http_request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="需要登录")

    try:
        success = await subagent_service.set_enabled(
            user_id, subagent_name, request.enabled
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not success:
        raise HTTPException(status_code=404, detail="Subagent not found")

    return {
        "message": f"Subagent {'enabled' if request.enabled else 'disabled'} successfully"
    }


@router.post("/agent/subagents", status_code=201)
async def create_subagent(
    request: CreateSubagentRequest,
    http_request: Request,
) -> SubagentSchema:
    """
    Create a custom subagent for the current user.

    **Request Body:**
    - `name`: Unique identifier (lowercase, underscores allowed)
    - `display_name`: Display name for UI
    - `description`: Description of what the subagent does
    - `system_prompt`: The system prompt for the subagent
    - `tools`: List of tool names the subagent can use
    - `max_iterations`: Maximum iterations (default: 10)
    - `category`: Category for organization (default: "custom")
    """
    user_id = getattr(http_request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="需要登录")

    try:
        config = await subagent_service.create_subagent(
            user_id=user_id,
            name=request.name,
            display_name=request.display_name,
            description=request.description,
            system_prompt=request.system_prompt,
            tools=request.tools,
            max_iterations=request.max_iterations,
            category=request.category,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return SubagentSchema(
        name=config.name,
        display_name=config.display_name,
        description=config.description,
        system_prompt=config.system_prompt,
        tools=config.tools,
        max_iterations=config.max_iterations,
        enabled=config.enabled,
        builtin=config.builtin,
        category=config.category,
    )


@router.put("/agent/subagents/{subagent_name}")
async def update_subagent(
    subagent_name: str,
    request: UpdateSubagentRequest,
    http_request: Request,
) -> SubagentSchema:
    """Update a custom subagent configuration."""
    user_id = getattr(http_request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="需要登录")

    update_data = request.model_dump(exclude_unset=True)

    try:
        config = await subagent_service.update_subagent(
            user_id=user_id,
            name=subagent_name,
            display_name=update_data.get("display_name"),
            description=update_data.get("description"),
            system_prompt=update_data.get("system_prompt"),
            tools=update_data.get("tools"),
            max_iterations=update_data.get("max_iterations"),
            category=update_data.get("category"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not config:
        raise HTTPException(status_code=404, detail="Subagent not found")

    return SubagentSchema(
        name=config.name,
        display_name=config.display_name,
        description=config.description,
        system_prompt=config.system_prompt,
        tools=config.tools,
        max_iterations=config.max_iterations,
        enabled=config.enabled,
        builtin=config.builtin,
        category=config.category,
    )


@router.delete("/agent/subagents/{subagent_name}")
async def delete_subagent(subagent_name: str, http_request: Request):
    """
    Delete a custom subagent.

    Note: Builtin subagents cannot be deleted, only disabled.

    **Parameters:**
    - `subagent_name`: The name of the subagent to delete
    """
    user_id = getattr(http_request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="需要登录")

    try:
        success = await subagent_service.delete_subagent(user_id, subagent_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not success:
        raise HTTPException(status_code=404, detail="Subagent not found")

    return {"message": "Subagent deleted successfully"}
