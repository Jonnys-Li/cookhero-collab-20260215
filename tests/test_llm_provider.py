from __future__ import annotations

import asyncio
import importlib
from types import SimpleNamespace

import pytest


def test_llm_provider_pick_model_and_create_llm(monkeypatch):
    provider_mod = importlib.import_module("app.llm.provider")

    created_kwargs: list[dict] = []

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            created_kwargs.append(kwargs)
            self.kwargs = kwargs

        def bind(self, **kwargs):
            # Return self for simplicity; invoker tests validate bind inputs separately.
            self.kwargs = {**self.kwargs, **kwargs}
            return self

        async def ainvoke(self, messages, **kwargs):
            return {"messages": messages, "kwargs": kwargs, "model": self.kwargs.get("model")}

    monkeypatch.setattr(provider_mod, "ChatOpenAI", FakeChatOpenAI)

    class FakeProfile:
        def __init__(self):
            self.model_names = ["m1", "m2"]
            self.api_key = "k"
            self.base_url = "https://example.com"
            self.temperature = 0.2
            self.max_tokens = 10
            self.request_timeout = 123

        def pick_default_model(self):
            return "m1"

    class FakeConfig:
        def get_profile(self, _llm_type=None):
            return FakeProfile()

    # Deterministic choice.
    monkeypatch.setattr(provider_mod.random, "choice", lambda xs: xs[0])

    provider = provider_mod.LLMProvider(FakeConfig())
    assert provider.pick_model("fast") == "m1"

    llm = provider.create_llm("fast", streaming=True, temperature=0.5, max_tokens=99)
    assert isinstance(llm, FakeChatOpenAI)
    assert created_kwargs
    assert created_kwargs[-1]["model"] == "m1"
    assert created_kwargs[-1]["streaming"] is True
    assert created_kwargs[-1]["timeout"] == 123
    assert created_kwargs[-1]["temperature"] == 0.5
    assert created_kwargs[-1]["max_completion_tokens"] == 99


def test_llm_provider_pick_model_raises_when_empty(monkeypatch):
    provider_mod = importlib.import_module("app.llm.provider")

    class EmptyProfile:
        model_names = []

    class FakeConfig:
        def get_profile(self, _llm_type=None):
            return EmptyProfile()

    provider = provider_mod.LLMProvider(FakeConfig())
    with pytest.raises(ValueError):
        _ = provider.pick_model("fast")


def test_llm_invoker_merges_callbacks_and_binds_tools(monkeypatch):
    provider_mod = importlib.import_module("app.llm.provider")

    bound: list[dict] = []
    invoked: list[dict] = []

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def bind(self, **kwargs):
            bound.append(kwargs)
            # Return a new instance to mirror LangChain bind chaining.
            return FakeChatOpenAI(**{**self.kwargs, **kwargs})

        async def ainvoke(self, messages, **kwargs):
            invoked.append({"messages": messages, "kwargs": kwargs, "model": self.kwargs.get("model")})
            return SimpleNamespace(content="ok")

        def astream(self, messages, **kwargs):
            _ = (messages, kwargs)
            async def _gen():
                yield SimpleNamespace(content="chunk")
            return _gen()

    class FakeProvider:
        def pick_model(self, _llm_type=None):
            return "m1"

    invoker = provider_mod.LLMInvoker(
        provider=FakeProvider(),
        llm_type="fast",
        base_llm=FakeChatOpenAI(model="base"),
        callbacks=["c1"],
    )

    async def _run():
        await invoker.ainvoke(["m"], config={"callbacks": ["c2"]})
        await invoker.ainvoke_with_tools(["m"], tools=[{"name": "t1"}], callbacks=["c3"])

    asyncio.run(_run())

    # First call binds the picked model.
    assert any(b.get("model") == "m1" for b in bound)
    # Second call should also bind tools.
    assert any("tools" in b for b in bound)

    # Callback merging: c3 (call) + c1 (invoker) ends up in config callbacks.
    assert invoked
    merged_callbacks = invoked[-1]["kwargs"]["config"]["callbacks"]
    assert merged_callbacks == ["c3", "c1"]

