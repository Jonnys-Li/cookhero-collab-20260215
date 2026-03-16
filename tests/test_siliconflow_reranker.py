from __future__ import annotations

import httpx

from langchain_core.documents import Document

from app.config.rag_config import RerankerConfig
from app.rag.rerankers.siliconflow_reranker import SiliconFlowReranker


def test_rerank_returns_empty_when_no_documents(run):
    reranker = SiliconFlowReranker(RerankerConfig(api_key="k"))

    async def _run():
        out = await reranker.rerank("q", [])
        assert out == []

    run(_run())


def test_rerank_falls_back_on_http_status_error(run, monkeypatch):
    reranker = SiliconFlowReranker(RerankerConfig(api_key="k", base_url="https://example.com/rerank"))
    docs = [Document(page_content="a", metadata={"dish_name": "A"})]

    class FakeResponse:
        def __init__(self):
            self.text = "boom"

        def raise_for_status(self):
            request = httpx.Request("POST", reranker.api_url)
            response = httpx.Response(500, request=request, text=self.text)
            raise httpx.HTTPStatusError("server error", request=request, response=response)

        def json(self):
            return {}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr("app.rag.rerankers.siliconflow_reranker.httpx.AsyncClient", lambda: FakeClient())

    async def _run():
        out = await reranker.rerank("q", docs)
        assert out is docs

    run(_run())


def test_rerank_falls_back_on_unexpected_exception(run, monkeypatch):
    reranker = SiliconFlowReranker(RerankerConfig(api_key="k", base_url="https://example.com/rerank"))
    docs = [Document(page_content="a", metadata={"dish_name": "A"})]

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *_args, **_kwargs):
            raise RuntimeError("network down")

    monkeypatch.setattr("app.rag.rerankers.siliconflow_reranker.httpx.AsyncClient", lambda: FakeClient())

    async def _run():
        out = await reranker.rerank("q", docs)
        assert out is docs

    run(_run())


def test_rerank_returns_empty_when_api_returns_no_results(run, monkeypatch):
    reranker = SiliconFlowReranker(RerankerConfig(api_key="k", base_url="https://example.com/rerank"))
    docs = [Document(page_content="a", metadata={"dish_name": "A"})]

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"results": []}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr("app.rag.rerankers.siliconflow_reranker.httpx.AsyncClient", lambda: FakeClient())

    async def _run():
        out = await reranker.rerank("q", docs)
        assert out == []

    run(_run())


def test_rerank_filters_and_sorts_by_score(run, monkeypatch):
    reranker = SiliconFlowReranker(
        RerankerConfig(
            api_key="k",
            base_url="https://example.com/rerank",
            score_threshold=0.2,
        )
    )
    docs = [
        Document(page_content="a", metadata={"dish_name": "A"}),
        Document(page_content="b", metadata={"dish_name": "B"}),
        Document(page_content="c", metadata={"dish_name": "C"}),
    ]

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "results": [
                    {"index": 0, "relevance_score": 0.21},
                    {"index": 2, "relevance_score": 0.35},
                    {"index": 1, "relevance_score": 0.01},
                ]
            }

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr("app.rag.rerankers.siliconflow_reranker.httpx.AsyncClient", lambda: FakeClient())

    async def _run():
        out = await reranker.rerank("q", docs)
        assert [doc.metadata.get("dish_name") for doc in out] == ["C", "A"]
        assert out[0].metadata["rerank_score"] == 0.35
        assert out[1].metadata["rerank_score"] == 0.21

    run(_run())
