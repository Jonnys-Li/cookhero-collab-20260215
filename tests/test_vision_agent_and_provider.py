from __future__ import annotations

import json
from contextlib import contextmanager
from types import SimpleNamespace

from app.config import settings
from app.vision.agent import VisionAgent, VisionIntent
from app.vision.provider import ImageInput, VisionProvider


def test_image_input_factories_and_message_content():
    url = ImageInput.from_url("https://example.com/x.jpg")
    assert url.to_message_content() == {
        "type": "image_url",
        "image_url": {"url": "https://example.com/x.jpg"},
    }

    b64 = ImageInput.from_base64("abc", mime_type="image/png")
    assert b64.to_message_content()["image_url"]["url"].startswith("data:image/png;base64,abc")

    by = ImageInput.from_bytes(b"hi", mime_type="image/jpeg")
    assert "data:image/jpeg;base64," in by.to_message_content()["image_url"]["url"]

    try:
        ImageInput().to_message_content()
        assert False, "Expected ValueError when neither url nor base64 is provided"
    except ValueError:
        pass


def test_vision_provider_validate_image(monkeypatch):
    fake_config = SimpleNamespace(
        supported_formats=["image/png"],
        max_image_size_mb=1,
    )
    monkeypatch.setattr(VisionProvider, "config", property(lambda _self: fake_config))

    provider = VisionProvider.__new__(VisionProvider)

    ok, err = provider.validate_image("image/png", 1024)
    assert ok is True
    assert err is None

    ok2, err2 = provider.validate_image("image/jpeg", 1024)
    assert ok2 is False
    assert "Unsupported image format" in (err2 or "")

    too_big, err3 = provider.validate_image("image/png", 2 * 1024 * 1024)
    assert too_big is False
    assert "Image too large" in (err3 or "")


def test_vision_provider_analyze_validations_and_happy_path(monkeypatch, run):
    import app.vision.provider as provider_mod

    fake_config = SimpleNamespace(
        api_key="",
        model_names=["vision-model"],
        supported_formats=["image/jpeg"],
        max_image_size_mb=1,
    )
    monkeypatch.setattr(VisionProvider, "config", property(lambda _self: fake_config))

    @contextmanager
    def dummy_llm_context(*_args, **_kwargs):  # noqa: ANN001
        yield None

    monkeypatch.setattr(provider_mod, "llm_context", dummy_llm_context)

    class DummyInvoker:
        async def ainvoke(self, *_args, **_kwargs):  # noqa: ANN001
            return SimpleNamespace(content='{"ok": true}')

    class DummyProvider:
        def create_invoker(self, llm_type: str):  # noqa: ANN001
            assert llm_type == "vision"
            return DummyInvoker()

    provider = VisionProvider.__new__(VisionProvider)
    provider._provider = DummyProvider()
    provider._invoker = None

    # Not enabled => runtime error.
    fake_config.api_key = ""
    try:
        run(provider.analyze(text="x", images=[ImageInput.from_url("https://example.com/x.jpg")]))
        assert False, "Expected RuntimeError when vision is disabled"
    except RuntimeError:
        pass

    # Enabled but no images => value error.
    fake_config.api_key = "k"
    try:
        run(provider.analyze(text="x", images=[]))
        assert False, "Expected ValueError when no images are provided"
    except ValueError:
        pass

    # Happy path => returns content string and memoizes invoker.
    out = run(provider.analyze(text="describe", images=[ImageInput.from_url("https://example.com/x.jpg")]))
    assert "ok" in out
    assert provider._invoker is not None


def test_vision_agent_parse_and_build_context(monkeypatch):
    # Make keyword checks deterministic.
    monkeypatch.setattr(settings.vision, "food_related_keywords", ["pizza"], raising=False)

    class DummyProvider:
        is_enabled = True

    agent = VisionAgent(provider=DummyProvider())

    # Non-JSON fallback: keyword => food-related.
    res_kw = agent._parse_response("pizza", user_query="")
    assert res_kw.is_food_related is True
    assert res_kw.intent == VisionIntent.FOOD_QUESTION
    assert res_kw.direct_response is None

    # Non-JSON fallback: no keyword => general image.
    res_no = agent._parse_response("a cat", user_query="")
    assert res_no.is_food_related is False
    assert res_no.intent == VisionIntent.GENERAL_IMAGE
    assert res_no.direct_response

    # Valid JSON should parse intent and extracted info.
    payload = {
        "is_food_related": True,
        "intent": "recipe_request",
        "description": "A bowl of ramen",
        "extracted_info": {"dish_name": "ramen", "ingredients": ["noodles", "egg"]},
        "direct_response": "should be ignored when food-related",
        "confidence": 0.9,
    }
    res = agent._parse_response(json.dumps(payload, ensure_ascii=False), user_query="")
    assert res.is_food_related is True
    assert res.intent == VisionIntent.RECIPE_REQUEST
    assert res.direct_response is None
    assert res.extracted_info.get("dish_name") == "ramen"

    ctx = agent.build_context_for_rag(res, user_query="how to cook?")
    assert "【图片内容】" in ctx
    assert "【识别菜品】" in ctx
    assert "【识别食材】" in ctx
    assert "【用户意图】" in ctx


def test_vision_agent_analyze_unavailable_and_error(run):
    class DisabledProvider:
        is_enabled = False

    agent = VisionAgent(provider=DisabledProvider())

    out = run(agent.analyze(images=[ImageInput.from_url("https://example.com/x.jpg")]))
    assert out.is_food_related is False
    assert out.intent == VisionIntent.UNCLEAR
    assert out.direct_response

    class ErrorProvider:
        is_enabled = True

        async def analyze(self, *args, **kwargs):  # noqa: ANN001
            raise RuntimeError("boom")

    agent2 = VisionAgent(provider=ErrorProvider())
    out2 = run(agent2.analyze(images=[ImageInput.from_url("https://example.com/x.jpg")]))
    assert out2.is_food_related is False
    assert out2.intent == VisionIntent.UNCLEAR
    assert "boom" in (out2.direct_response or "")
