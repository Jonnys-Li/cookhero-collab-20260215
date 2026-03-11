"""
MCP StreamableHTTP endpoint for diet budget adjustment tools.
"""

from __future__ import annotations

import json
import secrets
import uuid
from datetime import date, datetime
from typing import Any, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.config import settings
from app.diet.service import diet_service

router = APIRouter()

MCP_SESSION_HEADER = "Mcp-Session-Id"

EMOTION_DELTA_MAP = {
    "low": 50,
    "medium": 100,
    "high": 150,
}

GET_TODAY_BUDGET_TOOL = {
    "name": "get_today_budget",
    "description": "Get today's calorie budget status for a user.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string", "description": "User ID"},
            "target_date": {
                "type": "string",
                "description": "Optional date in YYYY-MM-DD format",
            },
        },
        "required": ["user_id"],
    },
}

AUTO_ADJUST_BUDGET_TOOL = {
    "name": "auto_adjust_today_budget",
    "description": (
        "Automatically adjust today's budget based on emotion level. "
        "Maps low/medium/high to 50/100/150 kcal."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string", "description": "User ID"},
            "emotion_level": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "description": "Emotion intensity level",
            },
            "reason": {"type": "string", "description": "Optional adjustment reason"},
            "target_date": {
                "type": "string",
                "description": "Optional date in YYYY-MM-DD format",
            },
        },
        "required": ["user_id", "emotion_level"],
    },
}

MCP_TOOL_SCHEMAS = [GET_TODAY_BUDGET_TOOL, AUTO_ADJUST_BUDGET_TOOL]


def _jsonrpc_success(
    request_id: Any,
    result: dict[str, Any],
    *,
    session_id: Optional[str] = None,
    status_code: int = 200,
) -> JSONResponse:
    headers: dict[str, str] = {}
    if session_id:
        headers[MCP_SESSION_HEADER] = session_id
    return JSONResponse(
        status_code=status_code,
        content={
            "jsonrpc": "2.0",
            "id": request_id,
            "result": result,
        },
        headers=headers,
    )


def _jsonrpc_error(
    request_id: Any,
    code: int,
    message: str,
    *,
    data: Any = None,
    status_code: int = 200,
) -> JSONResponse:
    payload: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {
            "code": code,
            "message": message,
        },
    }
    if data is not None:
        payload["error"]["data"] = data
    return JSONResponse(status_code=status_code, content=payload)


def _resolve_session_id(request: Request) -> str:
    return request.headers.get(MCP_SESSION_HEADER) or str(uuid.uuid4())


def _parse_target_date(target_date: Optional[str]) -> Optional[date]:
    if not target_date:
        return None
    try:
        return datetime.strptime(target_date, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("target_date 必须是 YYYY-MM-DD 格式") from exc


def _get_auth_header_name() -> str:
    configured = settings.MCP_DIET_AUTH_HEADER_NAME.strip()
    return configured or "X-MCP-Service-Key"


def _is_authorized(request: Request) -> tuple[bool, Optional[str]]:
    expected = settings.MCP_DIET_SERVICE_KEY.strip()
    if not expected:
        return False, "MCP_DIET_SERVICE_KEY 未配置"

    auth_header = _get_auth_header_name()
    provided = request.headers.get(auth_header, "").strip()
    if not provided:
        return False, f"缺少认证头 {auth_header}"

    if not secrets.compare_digest(provided, expected):
        return False, "MCP 服务密钥无效"

    return True, None


def _build_tool_content(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(data, ensure_ascii=False),
            }
        ],
        "isError": False,
    }


async def _execute_get_today_budget(arguments: dict[str, Any]) -> dict[str, Any]:
    user_id = str(arguments.get("user_id") or "").strip()
    if not user_id:
        raise ValueError("user_id 是必填参数")

    target_date = _parse_target_date(arguments.get("target_date"))
    budget = await diet_service.get_today_budget(
        user_id=user_id,
        target_date=target_date,
    )
    return _build_tool_content(
        {
            "message": "获取当天预算成功",
            "budget": budget,
        }
    )


async def _execute_auto_adjust_budget(arguments: dict[str, Any]) -> dict[str, Any]:
    user_id = str(arguments.get("user_id") or "").strip()
    if not user_id:
        raise ValueError("user_id 是必填参数")

    emotion_level = str(arguments.get("emotion_level") or "").strip().lower()
    if emotion_level not in EMOTION_DELTA_MAP:
        raise ValueError("emotion_level 必须是 low / medium / high")

    target_date = _parse_target_date(arguments.get("target_date"))
    reason = str(arguments.get("reason") or "").strip() or "情绪支持自动预算调整"
    requested_delta = EMOTION_DELTA_MAP[emotion_level]

    result = await diet_service.adjust_today_budget(
        user_id=user_id,
        delta_calories=requested_delta,
        reason=reason,
        target_date=target_date,
        source="emotion_budget_guard_mcp",
    )

    return _build_tool_content(
        {
            "message": "自动调整完成",
            "emotion_level": emotion_level,
            "requested_delta": requested_delta,
            "applied_delta": result.get("applied_delta"),
            "capped": result.get("capped"),
            "effective_goal": result.get("effective_goal"),
            "budget": result,
        }
    )


async def _handle_tools_call(arguments: dict[str, Any]) -> dict[str, Any]:
    tool_name = str(arguments.get("name") or "").strip()
    tool_args = arguments.get("arguments")

    if not tool_name:
        raise ValueError("tools/call 缺少 name")
    if tool_args is None:
        tool_args = {}
    if not isinstance(tool_args, dict):
        raise ValueError("tools/call 的 arguments 必须是对象")

    if tool_name == "get_today_budget":
        return await _execute_get_today_budget(tool_args)
    if tool_name == "auto_adjust_today_budget":
        return await _execute_auto_adjust_budget(tool_args)

    raise ValueError(f"未知工具: {tool_name}")


@router.post("/mcp/diet-adjust")
async def diet_adjust_mcp_endpoint(request: Request):
    """
    StreamableHTTP MCP endpoint for diet auto-adjustment tools.
    """
    session_id = _resolve_session_id(request)
    request_id: Any = None

    authorized, auth_error = _is_authorized(request)
    if not authorized:
        status_code = 503 if auth_error == "MCP_DIET_SERVICE_KEY 未配置" else 401
        return _jsonrpc_error(
            request_id,
            code=-32001,
            message=auth_error or "认证失败",
            status_code=status_code,
        )

    try:
        payload = await request.json()
    except Exception:
        return _jsonrpc_error(
            request_id,
            code=-32700,
            message="Invalid JSON payload",
            status_code=400,
        )

    if not isinstance(payload, dict):
        return _jsonrpc_error(
            request_id,
            code=-32600,
            message="Invalid Request",
            status_code=400,
        )

    request_id = payload.get("id")
    method = payload.get("method")
    params = payload.get("params") or {}

    if not isinstance(method, str):
        return _jsonrpc_error(request_id, code=-32600, message="Invalid Request")
    if not isinstance(params, dict):
        return _jsonrpc_error(request_id, code=-32602, message="Invalid params")

    try:
        if method == "initialize":
            return _jsonrpc_success(
                request_id,
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {"listChanged": False},
                    },
                    "serverInfo": {
                        "name": "cookhero-diet-adjust-mcp",
                        "version": "1.0.0",
                    },
                },
                session_id=session_id,
            )

        if method == "tools/list":
            return _jsonrpc_success(
                request_id,
                {"tools": MCP_TOOL_SCHEMAS},
                session_id=session_id,
            )

        if method == "tools/call":
            result = await _handle_tools_call(params)
            return _jsonrpc_success(request_id, result, session_id=session_id)

        return _jsonrpc_error(request_id, code=-32601, message=f"Method not found: {method}")

    except ValueError as exc:
        return _jsonrpc_error(request_id, code=-32602, message=str(exc))
    except Exception as exc:
        return _jsonrpc_error(
            request_id,
            code=-32000,
            message="MCP tool execution failed",
            data=str(exc),
        )
