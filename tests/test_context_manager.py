from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.context.manager import ContextManager


def test_context_manager_build_llm_messages_includes_expected_sections():
    cm = ContextManager(system_prompt="SYS")
    history = [
        {"role": "user", "content": "u0"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "u2"},
    ]

    messages = cm.build_llm_messages(
        history=history,
        compressed_count=1,
        compressed_summary="SUM",
        extra_prompt="EXTRA",
        user_profile="PROFILE",
        user_instruction="INSTR",
    )

    assert isinstance(messages[0], SystemMessage)
    assert "PROFILE" in messages[0].content
    assert "INSTR" in messages[0].content

    assert isinstance(messages[1], SystemMessage)
    assert messages[1].content == "SYS"

    assert isinstance(messages[2], SystemMessage)
    assert "SUM" in messages[2].content

    # Uncompressed messages: assistant then user
    assert any(isinstance(m, AIMessage) and m.content == "a1" for m in messages)
    assert any(isinstance(m, HumanMessage) and m.content == "u2" for m in messages)

    # Extra prompt is appended as an AI message.
    assert isinstance(messages[-1], AIMessage)
    assert messages[-1].content == "EXTRA"


def test_context_manager_build_history_text_marks_current_question_and_truncates():
    cm = ContextManager(system_prompt="SYS", history_text_max_len=5)

    assert cm.build_history_text(history=[], compressed_summary=None) == "(无历史对话)"
    assert cm._format_user_personalization(None, None) == ""

    history = [
        {"role": "user", "content": "1234567890"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "u2"},
    ]
    out = cm.build_history_text(history=history, compressed_summary="SUM")
    assert "[历史对话摘要]" in out
    assert "SUM" in out
    assert "[最近对话]" in out
    assert "user (**当前问题**)" in out
    assert "12345..." in out
