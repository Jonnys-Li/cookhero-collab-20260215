from __future__ import annotations

import json

from app.conversation.types import ChatContext, ExtraOptions
from app.services.conversation_service import conversation_service


def _make_ctx() -> ChatContext:
    return ChatContext(
        conv_id="c1",
        message="m",
        user_id="u1",
        options=ExtraOptions(),
        history=[],
        history_dicts=[],
        history_text="",
        compressed_summary=None,
        compressed_count=0,
    )


def test_emit_thinking_appends_step_and_emits_sse():
    ctx = _make_ctx()
    out = conversation_service._emit_thinking(ctx, "step1")
    assert ctx.thinking_steps == ["step1"]
    assert out.startswith("data: ")
    payload = json.loads(out[len("data: ") :].strip())
    assert payload["type"] == "thinking"
    assert payload["content"] == "step1"


def test_build_combined_context_prompt_orders_sections():
    prompt = conversation_service._build_combined_context_prompt(
        rag_context="RAG",
        web_context="WEB",
        rewritten_query="RQ",
        vision_context="VISION",
    )
    assert "【图片工具分析结果】" in prompt
    assert "【重写后的检索语句】" in prompt
    assert "【本地知识库工具分析结果】" in prompt
    assert "【互联网搜索工具分析结果】" in prompt


def test_format_content_with_sources_appends_appendix():
    content = "hello"
    sources = [
        {"type": "rag", "info": "Mapo tofu"},
        {"type": "web", "info": "Wikipedia", "url": "https://example.com"},
    ]
    out = conversation_service._format_content_with_sources(content, sources)
    assert out.startswith("hello")
    assert "参考来源" in out
    assert "知识库: Mapo tofu" in out
    assert "网络搜索: Wikipedia(https://example.com)" in out

