from fastapi import HTTPException
import pytest

from app.api.v1.endpoints import agent as agent_endpoint


def test_list_available_tools_includes_builtin_diet_mcp(monkeypatch, run, build_request):
    async_servers = [
        {
            "name": "builtin",
            "type": "local",
            "tools": [{"name": "diet_analysis", "description": "diet tool"}],
        },
        {
            "name": "diet_auto_adjust",
            "type": "mcp",
            "tools": [
                {
                    "name": "mcp_diet_auto_adjust_get_today_budget",
                    "description": "budget",
                }
            ],
        },
        {
            "name": "subagents",
            "type": "subagent",
            "tools": [{"name": "subagent_emotion_support", "description": "emotion"}],
        },
    ]
    monkeypatch.setattr(
        agent_endpoint.AgentHub,
        "list_all_servers",
        classmethod(lambda cls, user_id=None: async_servers),
    )

    response = run(agent_endpoint.list_available_tools(build_request()))

    names = [server.name for server in response.servers]
    assert "diet_auto_adjust" in names
    assert "subagents" not in names


def test_list_available_tools_requires_authentication(run, build_request):
    with pytest.raises(HTTPException) as exc_info:
        run(agent_endpoint.list_available_tools(build_request(user_id="")))
    assert exc_info.value.status_code == 401
    assert "需要登录" in str(exc_info.value.detail)
