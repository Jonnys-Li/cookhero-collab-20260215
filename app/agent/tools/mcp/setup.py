"""MCP server setup.

This module wires MCP servers into the unified AgentHub provider system.
"""

import logging

from app.agent.registry import AgentHub

logger = logging.getLogger(__name__)


async def register_amap_mcp() -> None:
    from app.config import settings

    if not settings.mcp.amap.enabled:
        logger.info("Amap MCP is disabled, skipping registration")
        return

    amap_key = settings.mcp.amap_api_key
    if not amap_key:
        logger.warning("AMAP_API_KEY not configured, skipping Amap MCP registration")
        return

    endpoint = f"https://mcp.amap.com/mcp?key={amap_key}"

    mcp_provider = AgentHub.get_provider("mcp")
    if not hasattr(mcp_provider, "register_server") or not hasattr(
        mcp_provider, "load_server_tools"
    ):
        raise RuntimeError("MCP provider does not support server management")

    getattr(mcp_provider, "register_server")("amap", endpoint)

    try:
        loaded = await getattr(mcp_provider, "load_server_tools")("amap")
        logger.info(f"Loaded {len(loaded)} tools from Amap MCP")
    except Exception as e:
        logger.error(f"Failed to load Amap MCP tools: {e}")
