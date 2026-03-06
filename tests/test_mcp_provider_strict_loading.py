import asyncio
import importlib.util
import sys
import types
from pathlib import Path

import pytest


def run(coro):
    return asyncio.run(coro)


def load_mcp_provider_module(monkeypatch):
    class FakeBaseTool:
        name = ""
        description = ""

    class FakeMCPTool(FakeBaseTool):
        def __init__(
            self,
            name: str,
            description: str,
            mcp_endpoint: str,
            mcp_tool_name: str,
            mcp_headers=None,
            parameters=None,
        ):
            self.name = name
            self.description = description
            self.mcp_endpoint = mcp_endpoint
            self.mcp_tool_name = mcp_tool_name
            self.mcp_headers = mcp_headers or {}
            self.parameters = parameters or {}

        def to_openai_schema(self):
            return {
                "type": "function",
                "function": {
                    "name": self.name,
                    "description": self.description,
                    "parameters": self.parameters,
                },
            }

    class FakeMCPClient:
        tools_payload = []
        initialize_error = None
        list_tools_error = None

        def __init__(self, endpoint: str, headers=None):
            self.endpoint = endpoint
            self.headers = headers or {}

        async def initialize(self):
            if FakeMCPClient.initialize_error:
                raise RuntimeError(FakeMCPClient.initialize_error)
            return {"ok": True}

        async def list_tools(self):
            if FakeMCPClient.list_tools_error:
                raise RuntimeError(FakeMCPClient.list_tools_error)
            return list(FakeMCPClient.tools_payload)

    fake_app = types.ModuleType("app")
    fake_app.__path__ = []

    fake_agent = types.ModuleType("app.agent")
    fake_agent.__path__ = []

    fake_agent_tools = types.ModuleType("app.agent.tools")
    fake_agent_tools.__path__ = []

    fake_agent_tools_base = types.ModuleType("app.agent.tools.base")
    fake_agent_tools_base.BaseTool = FakeBaseTool
    fake_agent_tools_base.MCPTool = FakeMCPTool

    fake_agent_tools_mcp = types.ModuleType("app.agent.tools.mcp")
    fake_agent_tools_mcp.__path__ = []

    fake_agent_tools_mcp_client = types.ModuleType("app.agent.tools.mcp.client")
    fake_agent_tools_mcp_client.MCPClient = FakeMCPClient

    monkeypatch.setitem(sys.modules, "app", fake_app)
    monkeypatch.setitem(sys.modules, "app.agent", fake_agent)
    monkeypatch.setitem(sys.modules, "app.agent.tools", fake_agent_tools)
    monkeypatch.setitem(sys.modules, "app.agent.tools.base", fake_agent_tools_base)
    monkeypatch.setitem(sys.modules, "app.agent.tools.mcp", fake_agent_tools_mcp)
    monkeypatch.setitem(
        sys.modules, "app.agent.tools.mcp.client", fake_agent_tools_mcp_client
    )

    module_name = "mcp_provider_under_test"
    monkeypatch.delitem(sys.modules, module_name, raising=False)

    provider_file = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "agent"
        / "tools"
        / "providers"
        / "mcp.py"
    )
    spec = importlib.util.spec_from_file_location(module_name, provider_file)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    return module, FakeMCPClient


def test_load_server_tools_strict_success(monkeypatch):
    module, fake_client = load_mcp_provider_module(monkeypatch)
    provider = module.MCPToolProvider()

    fake_client.tools_payload = [
        {
            "name": "hello",
            "description": "test tool",
            "inputSchema": {"type": "object", "properties": {}},
        }
    ]
    fake_client.initialize_error = None
    fake_client.list_tools_error = None

    provider.register_server("demo", "https://example.com/mcp")
    loaded = run(provider.load_server_tools("demo", strict=True))

    assert len(loaded) == 1
    assert loaded[0].name == "mcp_demo_hello"


def test_load_server_tools_strict_zero_tools_raises(monkeypatch):
    module, fake_client = load_mcp_provider_module(monkeypatch)
    provider = module.MCPToolProvider()

    fake_client.tools_payload = []
    fake_client.initialize_error = None
    fake_client.list_tools_error = None

    provider.register_server("demo", "https://example.com/mcp")
    with pytest.raises(module.MCPServerLoadError) as exc:
        run(provider.load_server_tools("demo", strict=True))

    assert exc.value.phase == "tools/list"
    assert exc.value.error_code == "zero_tools"


def test_load_server_tools_non_strict_zero_tools_returns_empty(monkeypatch):
    module, fake_client = load_mcp_provider_module(monkeypatch)
    provider = module.MCPToolProvider()

    fake_client.tools_payload = []
    fake_client.initialize_error = None
    fake_client.list_tools_error = None

    provider.register_server("demo", "https://example.com/mcp")
    loaded = run(provider.load_server_tools("demo", strict=False))

    assert loaded == []


def test_load_server_tools_strict_initialize_error(monkeypatch):
    module, fake_client = load_mcp_provider_module(monkeypatch)
    provider = module.MCPToolProvider()

    fake_client.tools_payload = []
    fake_client.initialize_error = "init failed"
    fake_client.list_tools_error = None

    provider.register_server("demo", "https://example.com/mcp")
    with pytest.raises(module.MCPServerLoadError) as exc:
        run(provider.load_server_tools("demo", strict=True))

    assert exc.value.phase == "initialize"
    assert exc.value.error_code == "initialize_failed"
