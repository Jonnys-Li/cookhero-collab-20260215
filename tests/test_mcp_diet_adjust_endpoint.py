import asyncio
import json

from starlette.requests import Request

from app.api.v1.endpoints import mcp as mcp_endpoint


def run(coro):
    return asyncio.run(coro)


def make_request(payload: dict, *, service_key: str = "test-key") -> Request:
    body = json.dumps(payload).encode("utf-8")
    headers = [(b"x-mcp-service-key", service_key.encode("utf-8"))]
    received = False

    async def receive():
        nonlocal received
        if received:
            return {"type": "http.request", "body": b"", "more_body": False}
        received = True
        return {"type": "http.request", "body": body, "more_body": False}

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/mcp/diet-adjust",
        "headers": headers,
    }
    return Request(scope, receive)


def parse_response(response):
    return json.loads(response.body.decode("utf-8"))


def parse_mcp_text_payload(response_body: dict) -> dict:
    text = response_body["result"]["content"][0]["text"]
    return json.loads(text)


def test_initialize_success(monkeypatch):
    monkeypatch.setattr(mcp_endpoint.settings, "MCP_DIET_SERVICE_KEY", "test-key")

    payload = {
        "jsonrpc": "2.0",
        "id": "req-1",
        "method": "initialize",
        "params": {},
    }
    response = run(mcp_endpoint.diet_adjust_mcp_endpoint(make_request(payload)))
    body = parse_response(response)

    assert response.status_code == 200
    assert body["id"] == "req-1"
    assert body["result"]["protocolVersion"] == "2024-11-05"
    assert "tools" in body["result"]["capabilities"]
    assert response.headers.get("Mcp-Session-Id")


def test_tools_list_returns_expected_tools(monkeypatch):
    monkeypatch.setattr(mcp_endpoint.settings, "MCP_DIET_SERVICE_KEY", "test-key")

    payload = {
        "jsonrpc": "2.0",
        "id": "req-2",
        "method": "tools/list",
        "params": {},
    }
    response = run(mcp_endpoint.diet_adjust_mcp_endpoint(make_request(payload)))
    body = parse_response(response)

    assert response.status_code == 200
    tools = body["result"]["tools"]
    names = {tool["name"] for tool in tools}
    assert names == {"get_today_budget", "auto_adjust_today_budget"}


def test_tools_call_get_today_budget(monkeypatch):
    monkeypatch.setattr(mcp_endpoint.settings, "MCP_DIET_SERVICE_KEY", "test-key")

    async def fake_get_today_budget(user_id: str, target_date=None):
        assert user_id == "u1"
        assert str(target_date) == "2026-03-06"
        return {
            "date": "2026-03-06",
            "base_goal": 1800,
            "today_adjustment": 50,
            "effective_goal": 1850,
            "remaining_adjustment_cap": 100,
            "adjustment_cap": 150,
        }

    monkeypatch.setattr(mcp_endpoint.diet_service, "get_today_budget", fake_get_today_budget)

    payload = {
        "jsonrpc": "2.0",
        "id": "req-3",
        "method": "tools/call",
        "params": {
            "name": "get_today_budget",
            "arguments": {
                "user_id": "u1",
                "target_date": "2026-03-06",
            },
        },
    }
    response = run(mcp_endpoint.diet_adjust_mcp_endpoint(make_request(payload)))
    body = parse_response(response)
    text_payload = parse_mcp_text_payload(body)

    assert response.status_code == 200
    assert body["result"]["isError"] is False
    assert text_payload["budget"]["effective_goal"] == 1850


def test_tools_call_auto_adjust_uses_emotion_mapping(monkeypatch):
    monkeypatch.setattr(mcp_endpoint.settings, "MCP_DIET_SERVICE_KEY", "test-key")

    async def fake_adjust_today_budget(
        user_id: str,
        delta_calories: int,
        reason=None,
        target_date=None,
        source="",
    ):
        assert user_id == "u1"
        assert delta_calories == 100
        assert reason == "今天有点焦虑"
        assert str(target_date) == "2026-03-06"
        assert source == "emotion_budget_guard_mcp"
        return {
            "date": "2026-03-06",
            "requested_delta": 100,
            "applied_delta": 100,
            "capped": False,
            "effective_goal": 1900,
        }

    monkeypatch.setattr(
        mcp_endpoint.diet_service,
        "adjust_today_budget",
        fake_adjust_today_budget,
    )

    payload = {
        "jsonrpc": "2.0",
        "id": "req-4",
        "method": "tools/call",
        "params": {
            "name": "auto_adjust_today_budget",
            "arguments": {
                "user_id": "u1",
                "emotion_level": "medium",
                "reason": "今天有点焦虑",
                "target_date": "2026-03-06",
            },
        },
    }
    response = run(mcp_endpoint.diet_adjust_mcp_endpoint(make_request(payload)))
    body = parse_response(response)
    text_payload = parse_mcp_text_payload(body)

    assert response.status_code == 200
    assert text_payload["requested_delta"] == 100
    assert text_payload["effective_goal"] == 1900


def test_invalid_service_key_returns_unauthorized(monkeypatch):
    monkeypatch.setattr(mcp_endpoint.settings, "MCP_DIET_SERVICE_KEY", "expected-key")

    payload = {
        "jsonrpc": "2.0",
        "id": "req-5",
        "method": "initialize",
    }
    response = run(
        mcp_endpoint.diet_adjust_mcp_endpoint(
            make_request(payload, service_key="wrong-key")
        )
    )
    body = parse_response(response)

    assert response.status_code == 401
    assert body["error"]["code"] == -32001
    assert "无效" in body["error"]["message"]


def test_missing_service_key_config_returns_503(monkeypatch):
    monkeypatch.setattr(mcp_endpoint.settings, "MCP_DIET_SERVICE_KEY", "")

    payload = {
        "jsonrpc": "2.0",
        "id": "req-6",
        "method": "initialize",
    }
    response = run(mcp_endpoint.diet_adjust_mcp_endpoint(make_request(payload)))
    body = parse_response(response)

    assert response.status_code == 503
    assert body["error"]["code"] == -32001
    assert "未配置" in body["error"]["message"]


def test_invalid_date_and_unknown_method_return_jsonrpc_error(monkeypatch):
    monkeypatch.setattr(mcp_endpoint.settings, "MCP_DIET_SERVICE_KEY", "test-key")

    bad_date_payload = {
        "jsonrpc": "2.0",
        "id": "req-7",
        "method": "tools/call",
        "params": {
            "name": "get_today_budget",
            "arguments": {
                "user_id": "u1",
                "target_date": "2026/03/06",
            },
        },
    }
    bad_date_response = run(
        mcp_endpoint.diet_adjust_mcp_endpoint(make_request(bad_date_payload))
    )
    bad_date_body = parse_response(bad_date_response)
    assert bad_date_body["error"]["code"] == -32602

    unknown_method_payload = {
        "jsonrpc": "2.0",
        "id": "req-8",
        "method": "foo/bar",
        "params": {},
    }
    unknown_method_response = run(
        mcp_endpoint.diet_adjust_mcp_endpoint(make_request(unknown_method_payload))
    )
    unknown_method_body = parse_response(unknown_method_response)
    assert unknown_method_body["error"]["code"] == -32601


def test_unknown_tool_returns_jsonrpc_error(monkeypatch):
    monkeypatch.setattr(mcp_endpoint.settings, "MCP_DIET_SERVICE_KEY", "test-key")

    payload = {
        "jsonrpc": "2.0",
        "id": "req-9",
        "method": "tools/call",
        "params": {
            "name": "unknown_tool",
            "arguments": {"user_id": "u1"},
        },
    }
    response = run(mcp_endpoint.diet_adjust_mcp_endpoint(make_request(payload)))
    body = parse_response(response)

    assert response.status_code == 200
    assert body["error"]["code"] == -32602
    assert "未知工具" in body["error"]["message"]
