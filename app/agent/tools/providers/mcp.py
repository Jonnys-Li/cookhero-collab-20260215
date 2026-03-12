"""MCP tool provider."""

from __future__ import annotations

import logging
from typing import Optional

from app.agent.tools.base import BaseTool, MCPTool
from app.agent.tools.mcp.client import MCPClient

logger = logging.getLogger(__name__)


class MCPServerLoadError(Exception):
    """Structured MCP server load error."""

    def __init__(
        self,
        *,
        server_name: str,
        phase: str,
        message: str,
        error_code: str = "load_failed",
    ):
        self.server_name = server_name
        self.phase = phase
        self.message = message
        self.error_code = error_code
        super().__init__(f"[{server_name}:{phase}] {message}")


class MCPToolProvider:
    name = "mcp"

    def __init__(self):
        self._tools: dict[str, MCPTool] = {}
        self._servers: dict[str, str] = {}
        self._server_headers: dict[str, dict[str, str]] = {}
        self._clients: dict[str, MCPClient] = {}

    # ----- server management -----

    def register_server(
        self, name: str, endpoint: str, headers: Optional[dict[str, str]] = None
    ) -> None:
        self._servers[name] = endpoint
        if headers:
            self._server_headers[name] = headers
        elif name in self._server_headers:
            del self._server_headers[name]
        if name in self._clients:
            del self._clients[name]

    def list_servers(self) -> list[str]:
        return list(self._servers.keys())

    def _get_client(self, name: str) -> Optional[MCPClient]:
        endpoint = self._servers.get(name)
        if not endpoint:
            return None
        if name not in self._clients:
            self._clients[name] = MCPClient(
                endpoint,
                headers=self._server_headers.get(name),
            )
        return self._clients[name]

    def _remove_server_tools(self, name: str) -> None:
        prefix = f"mcp_{name}_"
        for tool_name in list(self._tools.keys()):
            if tool_name.startswith(prefix):
                del self._tools[tool_name]

    async def load_server_tools(self, name: str, strict: bool = False) -> list[MCPTool]:
        client = self._get_client(name)
        if not client:
            message = "MCP server not registered"
            if strict:
                raise MCPServerLoadError(
                    server_name=name,
                    phase="register",
                    message=message,
                    error_code="not_registered",
                )
            logger.warning("%s: %s", message, name)
            return []

        try:
            self._remove_server_tools(name)
            try:
                await client.initialize()
            except Exception as exc:
                if strict:
                    raise MCPServerLoadError(
                        server_name=name,
                        phase="initialize",
                        message=str(exc),
                        error_code="initialize_failed",
                    ) from exc
                logger.exception(
                    "Failed to initialize MCP server %s: %s",
                    name,
                    exc,
                )
                return []

            try:
                tools = await client.list_tools()
            except Exception as exc:
                if strict:
                    raise MCPServerLoadError(
                        server_name=name,
                        phase="tools/list",
                        message=str(exc),
                        error_code="tools_list_failed",
                    ) from exc
                logger.exception(
                    "Failed to fetch tools/list from MCP server %s: %s",
                    name,
                    exc,
                )
                return []

            if not tools:
                if strict:
                    raise MCPServerLoadError(
                        server_name=name,
                        phase="tools/list",
                        message="MCP server returned zero tools",
                        error_code="zero_tools",
                    )
                logger.warning("MCP server %s returned zero tools", name)
                return []

            loaded: list[MCPTool] = []
            for tool_info in tools:
                tool_name = tool_info.get("name", "")
                if not tool_name:
                    continue
                full_tool_name = f"mcp_{name}_{tool_name}"

                mcp_tool = MCPTool(
                    name=full_tool_name,
                    description=tool_info.get("description", ""),
                    mcp_endpoint=self._servers[name],
                    mcp_tool_name=tool_name,
                    mcp_headers=self._server_headers.get(name),
                    parameters=tool_info.get("inputSchema", {}),
                )

                self._tools[mcp_tool.name] = mcp_tool
                loaded.append(mcp_tool)

            if not loaded:
                if strict:
                    raise MCPServerLoadError(
                        server_name=name,
                        phase="tools/list",
                        message="MCP server tools are invalid or empty",
                        error_code="invalid_tools",
                    )
                logger.warning("MCP server %s returned invalid tools payload", name)
                return []

            logger.info("Loaded %s tools from MCP server: %s", len(loaded), name)
            return loaded
        except Exception as e:
            if strict and isinstance(e, MCPServerLoadError):
                raise
            logger.exception("Failed to load tools from MCP server %s: %s", name, e)
            return []

    def unregister_server(self, name: str) -> None:
        self._remove_server_tools(name)
        if name in self._servers:
            del self._servers[name]
        if name in self._server_headers:
            del self._server_headers[name]
        if name in self._clients:
            del self._clients[name]

    # ----- ToolProvider surface -----

    def register_tool(self, tool: BaseTool) -> None:
        if not isinstance(tool, MCPTool):
            raise TypeError("MCPToolProvider only accepts MCPTool")
        self._tools[tool.name] = tool

    def unregister_tool(self, name: str) -> bool:
        if name in self._tools:
            del self._tools[name]
            return True
        return False

    def get_tool(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    def list_tool_names(self) -> list[str]:
        return list(self._tools.keys())

    def get_tool_schema(self, name: str) -> Optional[dict]:
        tool = self._tools.get(name)
        if not tool:
            return None
        return tool.to_openai_schema()

    def get_tool_schemas(self, names: Optional[list[str]] = None) -> list[dict]:
        if names is None:
            return [t.to_openai_schema() for t in self._tools.values()]
        return [self._tools[n].to_openai_schema() for n in names if n in self._tools]

    def list_servers_with_tools(self) -> list[dict]:
        """Return tools grouped by MCP server.

        Returns:
            List of server dicts, each containing:
            - name: server name
            - type: "mcp"
            - tools: list of tool info dicts
        """
        # Group tools by server.
        #
        # Important: even if a server has not loaded tools yet, keep it visible so the
        # frontend can show "configured/connecting" states (demo stability).
        servers: dict[str, list[dict]] = {name: [] for name in self._servers.keys()}
        known_servers = sorted(self._servers.keys(), key=len, reverse=True)

        for t in self._tools.values():
            # name format: mcp_{server}_{tool}
            server_name = None
            if t.name.startswith("mcp_"):
                for candidate in known_servers:
                    prefix = f"mcp_{candidate}_"
                    if t.name.startswith(prefix):
                        server_name = candidate
                        break

            if server_name is None:
                server_name = "unknown"

            if server_name not in servers:
                servers[server_name] = []

            servers[server_name].append(
                {
                    "name": t.name,
                    "description": t.description,
                }
            )

        # Convert to list format with stable ordering:
        # - registered servers in alphabetical order
        # - "unknown" (if any) at the end
        ordered_names = sorted([name for name in servers.keys() if name != "unknown"])
        if "unknown" in servers:
            ordered_names.append("unknown")
        return [
            {"name": name, "type": "mcp", "tools": servers.get(name, [])}
            for name in ordered_names
        ]
