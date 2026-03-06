"""
MCP server management service.
"""

from __future__ import annotations
import logging
import re
from typing import List

from sqlalchemy import select

from app.agent.database.models import AgentMCPServerModel
from app.agent.registry import AgentHub
from app.agent.tools.providers.mcp import MCPToolProvider, MCPServerLoadError
from app.database.session import get_session_context

logger = logging.getLogger(__name__)

NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{2,64}$")


class MCPService:
    """Service for managing user-defined MCP servers."""

    async def list_servers(self, user_id: str) -> List[AgentMCPServerModel]:
        async with get_session_context() as session:
            stmt = select(AgentMCPServerModel).where(
                AgentMCPServerModel.user_id == user_id
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def create_server(
        self,
        *,
        user_id: str,
        name: str,
        endpoint: str,
        enabled: bool = True,
        auth_header_name: str | None = None,
        auth_token: str | None = None,
    ) -> tuple[AgentMCPServerModel, list[str]]:
        self._validate_name(name)
        self._validate_endpoint(endpoint)
        self._validate_auth(auth_header_name, auth_token)

        loaded_tool_names: list[str] = []
        registration_attempted = False
        server = AgentMCPServerModel(
            user_id=user_id,
            name=name,
            endpoint=endpoint,
            auth_header_name=auth_header_name,
            auth_token=auth_token,
            enabled=enabled,
        )

        try:
            async with get_session_context() as session:
                existing_stmt = select(AgentMCPServerModel).where(
                    AgentMCPServerModel.user_id == user_id,
                    AgentMCPServerModel.name == name,
                )
                existing = (await session.execute(existing_stmt)).scalar_one_or_none()
                if existing:
                    raise ValueError("MCP 名称已存在")

                session.add(server)
                await session.flush()

                if enabled:
                    registration_attempted = True
                    loaded_tool_names = await self.register_server(server, strict=True)
        except Exception:
            if registration_attempted:
                self._unregister_server(name)
            raise

        return server, loaded_tool_names

    async def register_server(
        self,
        server: AgentMCPServerModel,
        *,
        strict: bool = False,
    ) -> list[str]:
        if not server.enabled:
            return []

        provider = self._get_provider()
        headers = self._build_headers(server)
        provider.register_server(server.name, server.endpoint, headers)

        try:
            loaded = await provider.load_server_tools(server.name, strict=strict)
        except MCPServerLoadError as exc:
            provider.unregister_server(server.name)
            logger.warning(
                "MCP server registration failed: server=%s endpoint=%s phase=%s error_code=%s error=%s",
                server.name,
                server.endpoint,
                exc.phase,
                exc.error_code,
                exc.message,
            )
            if strict:
                raise ValueError(
                    self._format_load_error(server.name, server.endpoint, exc)
                ) from exc
            return []

        loaded_tool_names = [tool.name for tool in loaded]
        if strict and not loaded_tool_names:
            provider.unregister_server(server.name)
            logger.warning(
                "MCP server registration failed: server=%s endpoint=%s phase=tools/list error_code=zero_tools",
                server.name,
                server.endpoint,
            )
            raise ValueError(
                f"MCP 服务器校验失败（{server.name}）：tools/list 阶段未返回可用工具"
            )
        return loaded_tool_names

    async def register_all_for_user(self, user_id: str) -> None:
        servers = await self.list_servers(user_id)
        for server in servers:
            if not server.enabled:
                continue
            try:
                await self.register_server(server)
            except Exception as exc:
                logger.warning(
                    "Failed to register MCP server %s for user %s: %s",
                    server.name,
                    user_id,
                    exc,
                )

    async def register_all(self) -> None:
        async with get_session_context() as session:
            stmt = select(AgentMCPServerModel).where(
                AgentMCPServerModel.enabled.is_(True)
            )
            result = await session.execute(stmt)
            servers = list(result.scalars().all())

        for server in servers:
            try:
                await self.register_server(server)
            except Exception as exc:
                logger.warning("Failed to register MCP server %s: %s", server.name, exc)

    async def update_server(
        self,
        *,
        user_id: str,
        name: str,
        endpoint: str | None = None,
        enabled: bool | None = None,
        auth_header_name: str | None = None,
        auth_token: str | None = None,
        update_auth: bool = False,
    ) -> tuple[AgentMCPServerModel, list[str]] | None:
        loaded_tool_names: list[str] = []
        registration_attempted = False
        should_unregister_after_commit = False

        try:
            async with get_session_context() as session:
                stmt = select(AgentMCPServerModel).where(
                    AgentMCPServerModel.user_id == user_id,
                    AgentMCPServerModel.name == name,
                )
                existing = (await session.execute(stmt)).scalar_one_or_none()
                if not existing:
                    return None

                if endpoint is not None:
                    self._validate_endpoint(endpoint)
                    existing.endpoint = endpoint

                if update_auth:
                    self._validate_auth(auth_header_name, auth_token)
                    existing.auth_header_name = auth_header_name
                    existing.auth_token = auth_token

                if enabled is not None:
                    existing.enabled = enabled

                should_revalidate = (
                    endpoint is not None or update_auth or enabled is not None
                )

                if existing.enabled and should_revalidate:
                    registration_attempted = True
                    loaded_tool_names = await self.register_server(existing, strict=True)
                elif not existing.enabled:
                    should_unregister_after_commit = True

                await session.flush()
        except Exception:
            if registration_attempted:
                self._unregister_server(name)
            raise

        if should_unregister_after_commit:
            self._unregister_server(name)

        return existing, loaded_tool_names

    async def delete_server(self, user_id: str, name: str) -> bool:
        async with get_session_context() as session:
            stmt = select(AgentMCPServerModel).where(
                AgentMCPServerModel.user_id == user_id,
                AgentMCPServerModel.name == name,
            )
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if not existing:
                return False

            await session.delete(existing)

        self._unregister_server(name)
        return True

    def _validate_name(self, name: str) -> None:
        if not NAME_PATTERN.match(name):
            raise ValueError("MCP 名称需为 2-64 位，支持字母、数字、_、-")

    def _validate_endpoint(self, endpoint: str) -> None:
        if not endpoint.startswith("http://") and not endpoint.startswith("https://"):
            raise ValueError("Endpoint 需要以 http:// 或 https:// 开头")
        if len(endpoint) > 512:
            raise ValueError("Endpoint 过长")

    def _validate_auth(
        self, auth_header_name: str | None, auth_token: str | None
    ) -> None:
        if not auth_header_name and not auth_token:
            return
        if not auth_header_name or not auth_token:
            raise ValueError("Header 名称和 Token 需要同时填写")
        if len(auth_header_name) > 128:
            raise ValueError("Header 名称过长")
        if "\n" in auth_header_name or "\r" in auth_header_name:
            raise ValueError("Header 名称不合法")

    def _build_headers(self, server: AgentMCPServerModel) -> dict[str, str] | None:
        if server.auth_header_name and server.auth_token:
            return {server.auth_header_name: server.auth_token}
        return None

    def _format_load_error(
        self,
        server_name: str,
        endpoint: str,
        exc: MCPServerLoadError,
    ) -> str:
        return (
            f"MCP 服务器校验失败（{server_name}）：{exc.phase} 阶段错误（{exc.error_code}）- "
            f"{exc.message}。endpoint={endpoint}"
        )

    def _get_provider(self) -> MCPToolProvider:
        return AgentHub.get_provider("mcp")  # type: ignore

    def _unregister_server(self, name: str) -> None:
        provider = self._get_provider()
        provider.unregister_server(name)


mcp_service = MCPService()
