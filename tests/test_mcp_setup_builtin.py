import importlib.util
import sys
import types
from pathlib import Path


def load_mcp_setup_module(monkeypatch):
    class FakeSettings:
        MCP_DIET_AUTO_REGISTER_ENABLED = True
        MCP_DIET_ENDPOINT = (
            "https://cookhero-collab-20260215.onrender.com/api/v1/mcp/diet-adjust"
        )
        MCP_DIET_AUTH_HEADER_NAME = "X-MCP-Service-Key"
        MCP_DIET_SERVICE_KEY = "cookhero-mcp-demo-key-v1"
        mcp = types.SimpleNamespace(
            amap=types.SimpleNamespace(enabled=False),
            amap_api_key="",
        )

    class FakeMCPToolProvider:
        pass

    class FakeAgentHub:
        _provider = None

        @classmethod
        def get_provider(cls, name: str):
            return cls._provider

    fake_app = types.ModuleType("app")
    fake_app.__path__ = []

    fake_agent = types.ModuleType("app.agent")
    fake_agent.__path__ = []

    fake_agent_registry = types.ModuleType("app.agent.registry")
    fake_agent_registry.AgentHub = FakeAgentHub

    fake_agent_tools = types.ModuleType("app.agent.tools")
    fake_agent_tools.__path__ = []

    fake_agent_tools_providers = types.ModuleType("app.agent.tools.providers")
    fake_agent_tools_providers.__path__ = []

    fake_agent_tools_providers_mcp = types.ModuleType("app.agent.tools.providers.mcp")
    fake_agent_tools_providers_mcp.MCPToolProvider = FakeMCPToolProvider

    fake_config = types.ModuleType("app.config")
    fake_config.settings = FakeSettings()

    monkeypatch.setitem(sys.modules, "app", fake_app)
    monkeypatch.setitem(sys.modules, "app.agent", fake_agent)
    monkeypatch.setitem(sys.modules, "app.agent.registry", fake_agent_registry)
    monkeypatch.setitem(sys.modules, "app.agent.tools", fake_agent_tools)
    monkeypatch.setitem(
        sys.modules, "app.agent.tools.providers", fake_agent_tools_providers
    )
    monkeypatch.setitem(
        sys.modules, "app.agent.tools.providers.mcp", fake_agent_tools_providers_mcp
    )
    monkeypatch.setitem(sys.modules, "app.config", fake_config)

    module_name = "mcp_setup_under_test"
    monkeypatch.delitem(sys.modules, module_name, raising=False)

    setup_file = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "agent"
        / "tools"
        / "mcp"
        / "setup.py"
    )
    spec = importlib.util.spec_from_file_location(module_name, setup_file)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    return module, fake_config.settings, FakeAgentHub


class FakeProvider:
    def __init__(self, *, raise_on_load: bool = False):
        self.raise_on_load = raise_on_load
        self.registered = []
        self.loaded_names = []
        self.unregistered = []

    def register_server(self, name: str, endpoint: str, headers=None):
        self.registered.append((name, endpoint, headers))

    async def load_server_tools(self, name: str):
        self.loaded_names.append(name)
        if self.raise_on_load:
            raise RuntimeError("load failed")
        return [types.SimpleNamespace(name=f"mcp_{name}_get_today_budget")]

    def unregister_server(self, name: str):
        self.unregistered.append(name)


def test_register_builtin_diet_mcp_success(monkeypatch, run):
    module, settings, hub = load_mcp_setup_module(monkeypatch)
    provider = FakeProvider()
    hub._provider = provider

    settings.MCP_DIET_AUTO_REGISTER_ENABLED = True
    settings.MCP_DIET_ENDPOINT = (
        "https://cookhero-collab-20260215.onrender.com/api/v1/mcp/diet-adjust"
    )
    settings.MCP_DIET_AUTH_HEADER_NAME = "X-MCP-Service-Key"
    settings.MCP_DIET_SERVICE_KEY = "demo-key"

    run(module._register_diet_auto_adjust_mcp())

    assert provider.registered
    name, endpoint, headers = provider.registered[0]
    assert name == "diet_auto_adjust"
    assert endpoint.endswith("/api/v1/mcp/diet-adjust")
    assert headers == {"X-MCP-Service-Key": "demo-key"}
    assert provider.loaded_names == ["diet_auto_adjust"]
    assert provider.unregistered == []


def test_register_builtin_diet_mcp_disabled(monkeypatch, run):
    module, settings, hub = load_mcp_setup_module(monkeypatch)
    provider = FakeProvider()
    hub._provider = provider

    settings.MCP_DIET_AUTO_REGISTER_ENABLED = False
    run(module._register_diet_auto_adjust_mcp())

    assert provider.registered == []
    assert provider.loaded_names == []


def test_register_builtin_diet_mcp_load_failure_unregisters(monkeypatch, run):
    module, settings, hub = load_mcp_setup_module(monkeypatch)
    provider = FakeProvider(raise_on_load=True)
    hub._provider = provider

    settings.MCP_DIET_AUTO_REGISTER_ENABLED = True
    settings.MCP_DIET_ENDPOINT = (
        "https://cookhero-collab-20260215.onrender.com/api/v1/mcp/diet-adjust"
    )
    settings.MCP_DIET_AUTH_HEADER_NAME = "X-MCP-Service-Key"
    settings.MCP_DIET_SERVICE_KEY = "demo-key"

    run(module._register_diet_auto_adjust_mcp())

    assert provider.registered
    assert provider.loaded_names == ["diet_auto_adjust"]
    assert provider.unregistered == ["diet_auto_adjust"]
