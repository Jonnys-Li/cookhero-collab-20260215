"""MCP server setup.

This module wires MCP servers into the unified AgentHub provider system.
"""

import logging

from app.agent.registry import AgentHub

logger = logging.getLogger(__name__)


async def register_mcp_servers() -> None:
    """注册所有 MCP 服务器。"""
    await _register_amap_mcp()
    await _register_diet_auto_adjust_mcp()
    await _register_custom_mcp_servers()


async def _register_custom_mcp_servers() -> None:
    """注册用户自定义 MCP 服务器。"""
    from app.services.mcp_service import mcp_service

    try:
        await mcp_service.register_all()
    except Exception as e:
        logger.warning(f"Failed to register custom MCP servers: {e}")


async def _register_amap_mcp() -> None:
    """注册高德地图 MCP 服务器。"""
    from app.config import settings
    from app.agent.tools.providers.mcp import MCPToolProvider

    if not settings.mcp.amap.enabled:
        logger.info("Amap MCP is disabled, skipping registration")
        return

    amap_key = settings.mcp.amap_api_key
    if not amap_key:
        logger.warning("AMAP_API_KEY not configured, skipping Amap MCP registration")
        return

    endpoint = f"https://mcp.amap.com/mcp?key={amap_key}"

    # 直接获取 MCPToolProvider 并调用方法
    mcp_provider: MCPToolProvider = AgentHub.get_provider("mcp")  # type: ignore
    mcp_provider.register_server("amap", endpoint)

    try:
        loaded = await mcp_provider.load_server_tools("amap")
        logger.info(f"Loaded {len(loaded)} tools from Amap MCP")
    except Exception as e:
        logger.error(f"Failed to load Amap MCP tools: {e}")


async def _register_diet_auto_adjust_mcp() -> None:
    """注册内置 diet_auto_adjust MCP 服务器。"""
    from app.config import settings
    from app.agent.tools.providers.mcp import MCPToolProvider

    if not settings.MCP_DIET_AUTO_REGISTER_ENABLED:
        logger.info("Built-in diet_auto_adjust MCP is disabled, skipping registration")
        return

    endpoint = settings.MCP_DIET_ENDPOINT.strip()
    if not endpoint:
        logger.warning("MCP_DIET_ENDPOINT not configured, skipping diet_auto_adjust MCP")
        return

    header_name = settings.MCP_DIET_AUTH_HEADER_NAME.strip() or "X-MCP-Service-Key"
    service_key = settings.MCP_DIET_SERVICE_KEY.strip()
    headers = {header_name: service_key} if service_key else None
    if not service_key:
        logger.warning(
            "MCP_DIET_SERVICE_KEY is empty; diet_auto_adjust MCP may fail auth"
        )

    mcp_provider: MCPToolProvider = AgentHub.get_provider("mcp")  # type: ignore
    mcp_provider.register_server("diet_auto_adjust", endpoint, headers)

    try:
        loaded = await mcp_provider.load_server_tools("diet_auto_adjust")
        if loaded:
            logger.info("Loaded %s tools from built-in diet_auto_adjust MCP", len(loaded))
        else:
            logger.warning(
                "Built-in diet_auto_adjust MCP registered but returned zero tools"
            )
    except Exception as exc:
        # Keep the server registered even if initial load fails so the frontend can
        # show "configured/connecting" state and the backend can retry later.
        logger.warning("Failed to load built-in diet_auto_adjust MCP: %s", exc)
