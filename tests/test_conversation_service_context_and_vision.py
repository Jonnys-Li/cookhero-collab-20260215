from __future__ import annotations

import json
from types import SimpleNamespace

import app.services.conversation_service as conversation_service_module
from app.conversation.types import ChatContext, ExtraOptions


def test_initialize_context_formats_history_and_loads_user_data(run, monkeypatch):
    class FakeConversationRepo:
        async def get_or_create(self, conversation_id, user_id=None):
            assert conversation_id is None
            assert user_id == "u1"
            return SimpleNamespace(id="c1")

        async def get_history(self, conv_id, limit=100):
            assert conv_id == "c1"
            assert limit == 100
            return [
                {"role": "assistant", "content": "hello", "sources": [{"type": "rag", "info": "x"}]},
                {"role": "user", "content": "hi"},
            ]

        async def get_compressed_summary(self, conv_id):
            assert conv_id == "c1"
            return ("SUM", 1)

    class FakeUser:
        profile = "P"
        user_instruction = "I"

    class FakeUserService:
        async def get_user_by_id(self, user_id):
            assert user_id == "u1"
            return FakeUser()

    fake_repo = FakeConversationRepo()
    fake_user_service = FakeUserService()

    monkeypatch.setattr(conversation_service_module, "conversation_repository", fake_repo)
    monkeypatch.setattr(conversation_service_module, "user_service", fake_user_service)
    monkeypatch.setattr(
        conversation_service_module.conversation_service.context_manager,
        "build_history_text",
        lambda **_kwargs: "HISTORY",
    )

    async def _run():
        ctx = await conversation_service_module.conversation_service._initialize_context(
            message="m1",
            conversation_id=None,
            user_id="u1",
            extra_options={"web_search": True},
            images=[{"data": "b64", "mime_type": "image/png"}],
        )

        assert ctx.conv_id == "c1"
        assert ctx.message == "m1"
        assert ctx.user_id == "u1"
        assert ctx.options.web_search is True
        assert ctx.compressed_summary == "SUM"
        assert ctx.compressed_count == 1
        assert ctx.history_text == "HISTORY"
        assert ctx.user_profile == "P"
        assert ctx.user_instruction == "I"
        assert ctx.images == [{"data": "b64", "mime_type": "image/png"}]

        # Assistant message should have sources appendix appended.
        assert "参考来源" in ctx.history_dicts[0]["content"]

    run(_run())


def test_save_user_message_persists_and_updates_context(run, monkeypatch):
    observed: dict[str, object] = {}

    class FakeConversationRepo:
        async def add_message(self, **kwargs):
            observed["add_message"] = kwargs

    monkeypatch.setattr(conversation_service_module, "conversation_repository", FakeConversationRepo())
    monkeypatch.setattr(
        conversation_service_module.conversation_service.context_manager,
        "build_history_text",
        lambda **_kwargs: "NEW_HISTORY",
    )

    async def _run():
        ctx = ChatContext(
            conv_id="c1",
            message="m1",
            user_id=None,
            options=ExtraOptions(),
            history=[],
            history_dicts=[],
            history_text="",
            compressed_summary=None,
            compressed_count=0,
            images=None,
        )

        await conversation_service_module.conversation_service._save_user_message(ctx)

        add_kwargs = observed["add_message"]
        assert add_kwargs["conversation_id"] == "c1"
        assert add_kwargs["role"] == "user"
        assert add_kwargs["content"] == "m1"
        assert add_kwargs["sources"] is None

        assert ctx.history[-1] == {"role": "user", "content": "m1"}
        assert ctx.history_dicts[-1] == {"role": "user", "content": "m1"}
        assert ctx.history_text == "NEW_HISTORY"

    run(_run())


def test_save_user_message_uploads_images_into_sources(run, monkeypatch):
    observed: dict[str, object] = {}

    class FakeConversationRepo:
        async def add_message(self, **kwargs):
            observed["add_message"] = kwargs

    async def fake_upload_to_imgbb(_data, _mime_type):
        return {
            "url": "https://img.example/u.png",
            "display_url": "https://img.example/u.png",
            "thumb_url": "https://img.example/t.png",
        }

    monkeypatch.setattr(conversation_service_module, "conversation_repository", FakeConversationRepo())
    monkeypatch.setattr("app.utils.image_storage.upload_to_imgbb", fake_upload_to_imgbb)

    async def _run():
        ctx = ChatContext(
            conv_id="c1",
            message="m1",
            user_id=None,
            options=ExtraOptions(),
            history=[],
            history_dicts=[],
            history_text="",
            compressed_summary=None,
            compressed_count=0,
            images=[{"data": "b64", "mime_type": "image/png"}],
        )

        await conversation_service_module.conversation_service._save_user_message(ctx)
        add_kwargs = observed["add_message"]
        assert add_kwargs["sources"] == [
            {
                "type": "image",
                "url": "https://img.example/u.png",
                "display_url": "https://img.example/u.png",
                "thumb_url": "https://img.example/t.png",
            }
        ]

    run(_run())


def test_process_vision_emits_events_and_sets_context(run, monkeypatch):
    class FakeIntent:
        value = "recipe_search"

    class FakeVisionResult:
        is_food_related = True
        intent = FakeIntent()
        description = "desc"
        confidence = 0.9

        def to_dict(self):
            return {
                "is_food_related": self.is_food_related,
                "intent": self.intent.value,
                "description": self.description,
                "confidence": self.confidence,
            }

    async def fake_analyze(**_kwargs):
        return FakeVisionResult()

    monkeypatch.setattr(
        conversation_service_module.ImageInput,
        "from_base64",
        classmethod(lambda cls, data, mime_type="image/jpeg": {"data": data, "mime_type": mime_type}),
    )
    monkeypatch.setattr(conversation_service_module.vision_agent, "analyze", fake_analyze)
    monkeypatch.setattr(conversation_service_module.vision_agent, "build_context_for_rag", lambda *_args, **_kwargs: "VISION_CTX")

    async def _collect():
        ctx = ChatContext(
            conv_id="c1",
            message="m1",
            user_id=None,
            options=ExtraOptions(),
            history=[],
            history_dicts=[],
            history_text="H",
            compressed_summary=None,
            compressed_count=0,
            images=[{"data": "b64", "mime_type": "image/png"}],
        )
        events = []
        async for event in conversation_service_module.conversation_service._process_vision(ctx):
            events.append(event)
        return ctx, events

    ctx, events = run(_collect())
    assert ctx.vision_result is not None
    assert ctx.vision_context == "VISION_CTX"
    assert any(event.startswith("data: ") and '"type": "vision"' in event for event in events)


def test_process_vision_is_resilient_to_errors(run, monkeypatch):
    async def fake_analyze(**_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        conversation_service_module.ImageInput,
        "from_base64",
        classmethod(lambda cls, data, mime_type="image/jpeg": {"data": data, "mime_type": mime_type}),
    )
    monkeypatch.setattr(conversation_service_module.vision_agent, "analyze", fake_analyze)

    async def _collect():
        ctx = ChatContext(
            conv_id="c1",
            message="m1",
            user_id=None,
            options=ExtraOptions(),
            history=[],
            history_dicts=[],
            history_text="H",
            compressed_summary=None,
            compressed_count=0,
            images=[{"data": "b64", "mime_type": "image/png"}],
        )
        events = []
        async for event in conversation_service_module.conversation_service._process_vision(ctx):
            events.append(event)
        return ctx, events

    ctx, events = run(_collect())
    assert ctx.vision_result is None
    assert any(
        json.loads(e[len("data: ") :].strip()).get("content", "").startswith("📷 图片分析出错")
        for e in events
        if e.startswith("data: ")
    )
