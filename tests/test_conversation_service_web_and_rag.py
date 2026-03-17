from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace


def _decode_sse(event: str) -> dict:
    assert event.startswith("data: ")
    return json.loads(event[len("data: ") :].strip())


def test_conversation_service_process_web_search_decision_emits_events(monkeypatch, run):
    import app.services.conversation_service as conv_mod
    from app.conversation.types import ChatContext, ExtraOptions
    from app.tools.web_search import WebSearchDecision, WebSearchParams

    service = conv_mod.conversation_service

    async def fake_decide_search(**_kwargs):
        return WebSearchDecision(
            confidence=7,
            search_params=WebSearchParams(query="q1", max_results=3),
            reason="needs web",
            raw={"x": 1},
        )

    monkeypatch.setattr(conv_mod.web_search_tool, "decide_search", fake_decide_search)
    monkeypatch.setattr(
        conv_mod.document_repository,
        "get_metadata_options",
        lambda **_kwargs: {"dish_name": ["d1"]},
    )

    ctx = ChatContext(
        conv_id="c1",
        message="m",
        user_id="u1",
        options=ExtraOptions(web_search=True),
        history=[],
        history_dicts=[],
        history_text="H",
        compressed_summary=None,
        compressed_count=0,
    )

    decision, events = run(service._process_web_search_decision(ctx))
    assert decision is not None
    assert decision.confidence == 7
    assert decision.search_params is not None
    assert decision.search_params.query == "q1"
    payloads = [_decode_sse(e) for e in events]
    assert all(p.get("type") == "thinking" for p in payloads)
    assert any("Web 搜索" in p.get("content", "") for p in payloads)


def test_conversation_service_execute_web_search_updates_context_and_sources(monkeypatch, run):
    import app.services.conversation_service as conv_mod
    from app.conversation.types import ChatContext, ExtraOptions
    from app.tools.web_search import WebSearchDecision, WebSearchParams, WebSearchResult

    service = conv_mod.conversation_service

    async def fake_execute_search(_params):
        return [
            WebSearchResult(
                title="T1",
                snippet="S1",
                source="example.com",
                url="https://example.com/1",
            ),
            WebSearchResult(
                title="T2",
                snippet="S2",
                source="example.com",
                url="https://example.com/2",
            ),
        ]

    monkeypatch.setattr(conv_mod.web_search_tool, "execute_search", fake_execute_search)
    monkeypatch.setattr(
        conv_mod.web_search_tool,
        "format_results_for_context",
        lambda _results: "WEB_CTX",
    )

    ctx = ChatContext(
        conv_id="c1",
        message="m",
        user_id="u1",
        options=ExtraOptions(web_search=True),
        history=[],
        history_dicts=[],
        history_text="H",
        compressed_summary=None,
        compressed_count=0,
    )

    decision = WebSearchDecision(
        confidence=7,
        search_params=WebSearchParams(query="q", max_results=2),
        reason="r",
        raw={},
    )

    events = run(service._execute_web_search(ctx, decision))
    assert ctx.web_search_context == "WEB_CTX"
    assert len(ctx.sources) == 2
    assert ctx.sources[0].type == "web"
    payloads = [_decode_sse(e) for e in events]
    assert any("Web 搜索" in p.get("content", "") for p in payloads)


def test_conversation_service_prepare_rag_context_rewrite_and_retrieve(monkeypatch, run):
    import app.services.conversation_service as conv_mod
    from app.conversation.types import ChatContext, ExtraOptions
    from app.services.rag_service import RetrievalResult

    service = conv_mod.conversation_service

    async def fake_rewrite(**_kwargs):
        return "rq"

    async def fake_retrieve(_query, **_kwargs):
        doc = SimpleNamespace(
            page_content="doc1 content",
            metadata={"dish_name": "Mapo", "difficulty": "easy", "category": "main"},
        )
        return RetrievalResult(
            original_query="q",
            rewritten_query="rq",
            context="RAG_CTX",
            documents=[doc],
            sources=[{"type": "rag", "info": "Mapo"}],
        )

    monkeypatch.setattr(service.query_rewriter, "rewrite", fake_rewrite)
    monkeypatch.setattr(conv_mod.rag_service_instance, "retrieve", fake_retrieve)

    ctx = ChatContext(
        conv_id="c1",
        message="m",
        user_id="u1",
        options=ExtraOptions(web_search=False),
        history=[],
        history_dicts=[],
        history_text="H",
        compressed_summary=None,
        compressed_count=0,
    )

    async def _collect():
        events = []
        async for event in service._prepare_rag_context(ctx, web_search_decision=None):
            events.append(event)
        return events

    events = run(_collect())
    assert ctx.rewritten_query == "rq"
    assert ctx.rag_context == "RAG_CTX"
    assert any(s.type == "rag" for s in ctx.sources)
    payloads = [_decode_sse(e) for e in events]
    assert any("检索到" in p.get("content", "") for p in payloads)


def test_conversation_service_rag_fallback_triggers_web_search(monkeypatch, run):
    import app.services.conversation_service as conv_mod
    from app.conversation.types import ChatContext, ExtraOptions
    from app.services.rag_service import RetrievalResult
    from app.tools.web_search import WebSearchDecision, WebSearchParams

    service = conv_mod.conversation_service

    async def fake_rewrite(**_kwargs):
        return "rq"

    async def fake_retrieve(_query, **_kwargs):
        return RetrievalResult(
            original_query="q",
            rewritten_query="rq",
            context="",
            documents=[],
            sources=[],
        )

    async def fake_execute_web_search(_ctx, _decision):
        # Make it obvious the fallback path executed.
        _ctx.web_search_context = "WEB_CTX"
        return ["data: " + json.dumps({"type": "thinking", "content": "fallback"}) + "\n\n"]

    monkeypatch.setattr(service.query_rewriter, "rewrite", fake_rewrite)
    monkeypatch.setattr(conv_mod.rag_service_instance, "retrieve", fake_retrieve)
    monkeypatch.setattr(service, "_execute_web_search", fake_execute_web_search)

    ctx = ChatContext(
        conv_id="c1",
        message="m",
        user_id="u1",
        options=ExtraOptions(web_search=True),
        history=[],
        history_dicts=[],
        history_text="H",
        compressed_summary=None,
        compressed_count=0,
    )
    decision = WebSearchDecision(
        confidence=10,
        search_params=WebSearchParams(query="q", max_results=2),
        reason="r",
        raw={},
    )

    async def _collect():
        events = []
        async for event in service._prepare_rag_context(ctx, web_search_decision=decision):
            events.append(event)
        return events

    events = run(_collect())
    assert ctx.web_search_context == "WEB_CTX"
    assert any("fallback" in e for e in events)


def test_conversation_service_generate_response_streams_chunks(monkeypatch, run):
    import app.services.conversation_service as conv_mod
    from app.conversation.types import ChatContext, ExtraOptions

    service = conv_mod.conversation_service

    monkeypatch.setattr(
        service.context_manager,
        "build_llm_messages",
        lambda *_args, **_kwargs: [{"role": "user", "content": "hi"}],
    )

    async def fake_stream(_messages, **_kwargs):
        yield "a"
        yield "b"

    monkeypatch.setattr(service.llm_orchestrator, "stream", fake_stream)

    ctx = ChatContext(
        conv_id="c1",
        message="m",
        user_id="u1",
        options=ExtraOptions(),
        history=[],
        history_dicts=[],
        history_text="H",
        compressed_summary=None,
        compressed_count=0,
    )

    async def _collect():
        chunks = []
        async for chunk in service._generate_response(ctx):
            chunks.append(chunk)
        return chunks

    chunks = run(_collect())
    assert chunks == ["a", "b"]


def test_conversation_service_save_response_schedules_evaluation(monkeypatch, run):
    import app.services.conversation_service as conv_mod
    from app.conversation.types import ChatContext, ExtraOptions, UnifiedSource

    service = conv_mod.conversation_service

    saved = {"add": None}
    scheduled = {"called": 0, "kwargs": None}
    tasks = []

    async def fake_add_message(**kwargs):
        saved["add"] = kwargs
        return SimpleNamespace(id="m1")

    async def fake_schedule_evaluation(**kwargs):
        scheduled["called"] += 1
        scheduled["kwargs"] = kwargs

    def fake_create_task(coro):
        t = asyncio.get_running_loop().create_task(coro)
        tasks.append(t)
        return t

    monkeypatch.setattr(conv_mod.conversation_repository, "add_message", fake_add_message)
    monkeypatch.setattr(conv_mod.evaluation_service, "schedule_evaluation", fake_schedule_evaluation)
    monkeypatch.setattr(conv_mod.asyncio, "create_task", fake_create_task)

    ctx = ChatContext(
        conv_id="c1",
        message="q",
        user_id="u1",
        options=ExtraOptions(),
        history=[],
        history_dicts=[],
        history_text="H",
        compressed_summary=None,
        compressed_count=0,
    )
    ctx.sources = [UnifiedSource(type="rag", info="Doc")]
    ctx.rag_context = "CTX"
    ctx.rewritten_query = "RQ"
    ctx.thinking_start_time = 1.0
    ctx.thinking_end_time = 1.1
    ctx.answer_start_time = 2.0
    ctx.answer_end_time = 2.2

    intent_result = SimpleNamespace(
        need_rag=True,
        intent=SimpleNamespace(value="recipe_search"),
        reason="r",
    )

    async def _run():
        await service._save_response(ctx, "hello", intent_result)
        # Ensure scheduled background evaluation has a chance to run.
        for t in tasks:
            await t

    run(_run())

    assert saved["add"] is not None
    assert saved["add"]["role"] == "assistant"
    assert saved["add"]["content"] == "hello"
    assert saved["add"]["intent"] == "recipe_search"
    assert isinstance(saved["add"]["thinking_duration_ms"], int)
    assert isinstance(saved["add"]["answer_duration_ms"], int)

    assert scheduled["called"] == 1
    assert scheduled["kwargs"] is not None
    assert scheduled["kwargs"]["message_id"] == "m1"
    assert scheduled["kwargs"]["conversation_id"] == "c1"
    assert scheduled["kwargs"]["query"] == "q"
    assert scheduled["kwargs"]["context"] == "CTX"
    assert scheduled["kwargs"]["response"] == "hello"
    assert scheduled["kwargs"]["rewritten_query"] == "RQ"
    assert scheduled["kwargs"]["user_id"] == "u1"


def test_conversation_service_handle_non_food_image_short_circuits(monkeypatch, run):
    import app.services.conversation_service as conv_mod
    from app.conversation.types import ChatContext, ExtraOptions

    service = conv_mod.conversation_service

    saved = {"add": None}

    async def fake_add_message(**kwargs):
        saved["add"] = kwargs
        return SimpleNamespace(id="m1")

    monkeypatch.setattr(conv_mod.conversation_repository, "add_message", fake_add_message)

    ctx = ChatContext(
        conv_id="c1",
        message="m",
        user_id="u1",
        options=ExtraOptions(),
        history=[],
        history_dicts=[],
        history_text="H",
        compressed_summary=None,
        compressed_count=0,
    )
    ctx.vision_result = SimpleNamespace(
        is_food_related=False,
        direct_response="not food",
        intent=SimpleNamespace(value="general_image"),
    )
    ctx.thinking_steps = []
    ctx.thinking_start_time = 0.0
    ctx.thinking_end_time = 0.1
    ctx.answer_start_time = 0.2
    ctx.answer_end_time = 0.3

    async def _collect():
        events = []
        async for event in service._handle_non_food_image(ctx):
            events.append(event)
        return events

    events = run(_collect())
    assert any('"type": "text"' in e for e in events)
    assert any('"type": "sources"' in e for e in events)
    assert any('"type": "done"' in e for e in events)
    assert saved["add"] is not None
    assert saved["add"]["role"] == "assistant"
    assert saved["add"]["content"] == "not food"
