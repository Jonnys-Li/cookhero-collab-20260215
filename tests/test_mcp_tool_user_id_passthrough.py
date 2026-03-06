import asyncio
import importlib.util
import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def run(coro):
    return asyncio.run(coro)


def load_mcp_base_module(monkeypatch):
    @dataclass
    class FakeToolResult:
        success: bool
        data: Optional[dict] = None
        error: Optional[str] = None

    class FakeMCPClient:
        last_call = {}

        def __init__(self, endpoint: str, headers=None):
            self.endpoint = endpoint
            self.headers = headers or {}

        async def call_tool(self, name: str, arguments: dict):
            FakeMCPClient.last_call = {
                "name": name,
                "arguments": dict(arguments),
            }
            return FakeToolResult(success=True, data={"ok": True})

    fake_app = types.ModuleType("app")
    fake_app.__path__ = []

    fake_agent = types.ModuleType("app.agent")
    fake_agent.__path__ = []

    fake_agent_tools = types.ModuleType("app.agent.tools")
    fake_agent_tools.__path__ = []

    fake_agent_tools_mcp = types.ModuleType("app.agent.tools.mcp")
    fake_agent_tools_mcp.__path__ = []

    fake_types_module = types.ModuleType("app.agent.types")
    fake_types_module.ToolResult = FakeToolResult

    fake_client_module = types.ModuleType("app.agent.tools.mcp.client")
    fake_client_module.MCPClient = FakeMCPClient

    monkeypatch.setitem(sys.modules, "app", fake_app)
    monkeypatch.setitem(sys.modules, "app.agent", fake_agent)
    monkeypatch.setitem(sys.modules, "app.agent.types", fake_types_module)
    monkeypatch.setitem(sys.modules, "app.agent.tools", fake_agent_tools)
    monkeypatch.setitem(sys.modules, "app.agent.tools.mcp", fake_agent_tools_mcp)
    monkeypatch.setitem(sys.modules, "app.agent.tools.mcp.client", fake_client_module)

    module_name = "mcp_base_under_test"
    monkeypatch.delitem(sys.modules, module_name, raising=False)

    base_file = Path(__file__).resolve().parents[1] / "app" / "agent" / "tools" / "base.py"
    spec = importlib.util.spec_from_file_location(module_name, base_file)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    return module, FakeMCPClient


def test_mcp_tool_keeps_user_id_when_schema_declares_it(monkeypatch):
    module, fake_client = load_mcp_base_module(monkeypatch)
    mcp_tool = module.MCPTool(
        name="mcp_demo_adjust",
        description="demo",
        mcp_endpoint="https://example.com/mcp",
        mcp_tool_name="auto_adjust_today_budget",
        parameters={
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "emotion_level": {"type": "string"},
            },
            "required": ["user_id", "emotion_level"],
        },
    )

    result = run(mcp_tool.execute(user_id="u1", emotion_level="medium"))

    assert result.success is True
    assert fake_client.last_call["name"] == "auto_adjust_today_budget"
    assert fake_client.last_call["arguments"]["user_id"] == "u1"
    assert fake_client.last_call["arguments"]["emotion_level"] == "medium"


def test_mcp_tool_strips_user_id_when_schema_missing_it(monkeypatch):
    module, fake_client = load_mcp_base_module(monkeypatch)
    mcp_tool = module.MCPTool(
        name="mcp_demo_weather",
        description="demo",
        mcp_endpoint="https://example.com/mcp",
        mcp_tool_name="weather_lookup",
        parameters={
            "type": "object",
            "properties": {
                "city": {"type": "string"},
            },
            "required": ["city"],
        },
    )

    result = run(mcp_tool.execute(user_id="u1", city="Shanghai"))

    assert result.success is True
    assert fake_client.last_call["name"] == "weather_lookup"
    assert "user_id" not in fake_client.last_call["arguments"]
    assert fake_client.last_call["arguments"]["city"] == "Shanghai"
