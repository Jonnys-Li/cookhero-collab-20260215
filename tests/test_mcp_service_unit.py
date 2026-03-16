from __future__ import annotations

import asyncio

import pytest

from app.agent.database.models import AgentMCPServerModel
from app.agent.tools.providers.mcp import MCPServerLoadError
from app.services.mcp_service import MCPService


class FakeTool:
    def __init__(self, name: str):
        self.name = name


class FakeProvider:
    def __init__(self):
        self.registered = {}
        self.unregistered = []
        self.loaded = []
        self.raise_load: MCPServerLoadError | None = None

    def register_server(self, name: str, endpoint: str, headers=None):
        self.registered[name] = {"endpoint": endpoint, "headers": headers}

    def unregister_server(self, name: str):
        self.unregistered.append(name)

    async def load_server_tools(self, name: str, strict: bool = False):
        _ = strict
        if self.raise_load:
            raise self.raise_load
        return self.loaded


def test_mcp_service_validations():
    service = MCPService()
    service._validate_name("ok_name-1")

    with pytest.raises(ValueError):
        service._validate_name("!")

    service._validate_endpoint("https://example.com")
    with pytest.raises(ValueError):
        service._validate_endpoint("ftp://example.com")

    service._validate_auth(None, None)
    with pytest.raises(ValueError):
        service._validate_auth("X-Token", None)


def test_mcp_service_register_server_success(monkeypatch):
    provider = FakeProvider()
    provider.loaded = [FakeTool("mcp_s1_weather"), FakeTool("mcp_s1_geo")]

    service = MCPService()
    monkeypatch.setattr(service, "_get_provider", lambda: provider)

    server = AgentMCPServerModel(
        user_id="u1",
        name="s1",
        endpoint="https://example.com",
        enabled=True,
        auth_header_name="X-Token",
        auth_token="t1",
    )

    async def _run():
        tools = await service.register_server(server, strict=True)
        assert tools == ["mcp_s1_weather", "mcp_s1_geo"]
        assert provider.registered["s1"]["headers"] == {"X-Token": "t1"}

    asyncio.run(_run())


def test_mcp_service_register_server_strict_raises_on_load_error(monkeypatch):
    provider = FakeProvider()
    provider.raise_load = MCPServerLoadError(
        server_name="s1",
        phase="initialize",
        message="bad",
        error_code="initialize_failed",
    )

    service = MCPService()
    monkeypatch.setattr(service, "_get_provider", lambda: provider)

    server = AgentMCPServerModel(
        user_id="u1",
        name="s1",
        endpoint="https://example.com",
        enabled=True,
    )

    async def _run():
        with pytest.raises(ValueError) as exc:
            await service.register_server(server, strict=True)
        assert "MCP 服务器校验失败" in str(exc.value)
        assert provider.unregistered == ["s1"]

    asyncio.run(_run())


def test_mcp_service_register_server_strict_raises_on_zero_tools(monkeypatch):
    provider = FakeProvider()
    provider.loaded = []

    service = MCPService()
    monkeypatch.setattr(service, "_get_provider", lambda: provider)

    server = AgentMCPServerModel(
        user_id="u1",
        name="s1",
        endpoint="https://example.com",
        enabled=True,
    )

    async def _run():
        with pytest.raises(ValueError) as exc:
            await service.register_server(server, strict=True)
        assert "tools/list" in str(exc.value)
        assert provider.unregistered == ["s1"]

    asyncio.run(_run())

