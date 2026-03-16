from __future__ import annotations

import asyncio

from app.services.evaluation_service import FilteredChatOpenAI


def test_filtered_chat_openai_filters_kwargs_injects_callbacks_and_forwards_attrs():
    calls: list[tuple[str, dict]] = []
    cb = object()

    class BoundLLM:
        def __init__(self, bound_kwargs: dict):
            self.bound_kwargs = bound_kwargs

        def invoke(self, *args, **kwargs):
            calls.append(("invoke(bound)", kwargs))
            return "ok"

    class FakeBaseLLM:
        model_name = "m1"
        temperature = 0.1
        custom_attr = 123

        def invoke(self, *args, **kwargs):
            calls.append(("invoke", kwargs))
            return "ok"

        async def ainvoke(self, *args, **kwargs):
            calls.append(("ainvoke", kwargs))
            return "aok"

        def generate(self, *args, **kwargs):
            calls.append(("generate", kwargs))
            return "gok"

        async def agenerate(self, *args, **kwargs):
            calls.append(("agenerate", kwargs))
            return "agok"

        def generate_prompt(self, *args, **kwargs):
            calls.append(("generate_prompt", kwargs))
            return "gpok"

        async def agenerate_prompt(self, *args, **kwargs):
            calls.append(("agenerate_prompt", kwargs))
            return "agpok"

        def bind(self, **kwargs):
            calls.append(("bind", kwargs))
            return BoundLLM(kwargs)

    wrapper = FilteredChatOpenAI(FakeBaseLLM(), callbacks=[cb])
    assert wrapper.model_name == "m1"
    assert wrapper.temperature == 0.1
    assert wrapper.custom_attr == 123

    out = wrapper.invoke("x", n=2, foo=1)
    assert out == "ok"
    assert calls[-1][0] == "invoke"
    assert calls[-1][1]["foo"] == 1
    assert "n" not in calls[-1][1]
    assert calls[-1][1]["callbacks"] == [cb]

    async def _run_async():
        out2 = await wrapper.ainvoke("x", n=3)
        assert out2 == "aok"
        assert calls[-1][0] == "ainvoke"
        assert "n" not in calls[-1][1]

        _ = wrapper.generate("x", n=4)
        assert calls[-1][0] == "generate"
        assert "n" not in calls[-1][1]

        _ = await wrapper.agenerate("x", n=5)
        assert calls[-1][0] == "agenerate"

        _ = wrapper.generate_prompt("x", n=6)
        assert calls[-1][0] == "generate_prompt"

        _ = await wrapper.agenerate_prompt("x", n=7)
        assert calls[-1][0] == "agenerate_prompt"

        bound = wrapper.bind(n=9, foo=2)
        assert isinstance(bound, FilteredChatOpenAI)
        # Underlying base bind should have filtered kwargs + callbacks.
        assert calls[-1][0] == "bind"
        assert calls[-1][1]["foo"] == 2
        assert "n" not in calls[-1][1]
        assert calls[-1][1]["callbacks"] == [cb]

        assert bound.invoke("x") == "ok"
        assert calls[-1][0] == "invoke(bound)"

    asyncio.run(_run_async())

