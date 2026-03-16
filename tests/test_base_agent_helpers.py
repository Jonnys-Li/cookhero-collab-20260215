from __future__ import annotations

from types import SimpleNamespace

from app.agent.agents.base import BaseAgent
from app.agent.types import AgentConfig, AgentContext, ToolCallInfo, ToolResultInfo


def _make_agent() -> BaseAgent:
    return BaseAgent(
        AgentConfig(
            name="t1",
            description="d",
            system_prompt="s",
            tools=[],
            max_iterations=1,
        )
    )


def test_get_forced_tool_call_prefers_sequence_over_single_name():
    agent = _make_agent()
    ctx = AgentContext(
        system_prompt="s",
        user_id="u1",
        session_id="sess",
        available_tools=[],
        force_tool_calls=[
            {"name": "tool_a", "arguments": {"x": 1}},
            {"name": "tool_b", "arguments": {"y": 2}},
        ],
        force_tool_name="tool_b",
        force_tool_arguments={"y": 99},
    )

    tc0 = agent._get_forced_tool_call(context=ctx, iteration=0, selected_tool_names=["tool_a", "tool_b"])
    assert tc0 is not None
    assert tc0.name == "tool_a"
    assert tc0.arguments == {"x": 1}

    tc1 = agent._get_forced_tool_call(context=ctx, iteration=1, selected_tool_names=["tool_a", "tool_b"])
    assert tc1 is not None
    assert tc1.name == "tool_b"

    tc2 = agent._get_forced_tool_call(context=ctx, iteration=2, selected_tool_names=["tool_a", "tool_b"])
    assert tc2 is None


def test_get_forced_tool_call_uses_single_name_only_on_iteration_zero():
    agent = _make_agent()
    ctx = AgentContext(
        system_prompt="s",
        force_tool_name="tool_a",
        force_tool_arguments={"x": 1},
    )
    tc0 = agent._get_forced_tool_call(context=ctx, iteration=0, selected_tool_names=["tool_a"])
    assert tc0 is not None
    assert tc0.name == "tool_a"
    assert tc0.arguments == {"x": 1}

    tc1 = agent._get_forced_tool_call(context=ctx, iteration=1, selected_tool_names=["tool_a"])
    assert tc1 is None


def test_parse_streaming_tool_calls_merges_args_and_handles_bad_json():
    agent = _make_agent()
    collected = [
        {"index": 0, "id": "c0", "name": "tool_a", "args": "{\"a\":"},
        {"index": 0, "args": " 1}"},
        {"index": 1, "id": "c1", "name": "tool_b", "args": "not json"},
    ]
    out = agent._parse_streaming_tool_calls(collected)
    assert out == [
        ToolCallInfo(id="c0", name="tool_a", arguments={"a": 1}),
        ToolCallInfo(id="c1", name="tool_b", arguments={}),
    ]


def test_append_tool_messages_handles_tool_calls_and_results():
    agent = _make_agent()
    messages: list[dict] = []
    response = SimpleNamespace(
        content="hello",
        tool_calls=[{"id": "x", "type": "function"}],
    )
    results = [
        ToolResultInfo(tool_call_id="x", name="tool_a", success=True, result={"ok": True}),
        ToolResultInfo(tool_call_id="y", name="tool_b", success=False, result=None, error="boom"),
    ]

    out = agent._append_tool_messages(messages, response, results)
    assert out is messages
    assert messages[0]["role"] == "assistant"
    assert messages[0]["tool_calls"] == response.tool_calls
    assert messages[0]["content"] is None
    assert messages[1]["role"] == "tool"
    assert messages[1]["tool_call_id"] == "x"
    assert "\"ok\": true" in messages[1]["content"].lower()
    assert messages[2]["content"].startswith("Error:")


def test_append_tool_messages_streaming_builds_tool_call_schema():
    agent = _make_agent()
    messages: list[dict] = []
    tool_calls = [
        ToolCallInfo(id="t1", name="tool_a", arguments={"x": 1}),
    ]
    results = [
        ToolResultInfo(tool_call_id="t1", name="tool_a", success=True, result={"ok": True}),
    ]
    out = agent._append_tool_messages_streaming(messages, "ignored", tool_calls, results)
    assert out is messages
    assert messages[0]["role"] == "assistant"
    assert messages[0]["content"] is None
    assert messages[0]["tool_calls"][0]["function"]["name"] == "tool_a"
    assert messages[1]["role"] == "tool"
    assert messages[1]["tool_call_id"] == "t1"


def test_extract_content_prefers_content_attribute():
    agent = _make_agent()
    assert agent._extract_content(SimpleNamespace(content="hi")) == "hi"
    assert agent._extract_content(123) == "123"
