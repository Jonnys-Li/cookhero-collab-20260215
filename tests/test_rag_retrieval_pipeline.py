from __future__ import annotations

import asyncio
from dataclasses import dataclass

from langchain_core.documents import Document

from app.rag.pipeline.retrieval import RetrievalOptimizationModule


@dataclass
class _Call:
    args: tuple
    kwargs: dict


class FakeVectorStore:
    def __init__(self, *, fail_hybrid: bool = False):
        self.fail_hybrid = fail_hybrid
        self.calls: list[_Call] = []

    def similarity_search_with_score(self, **kwargs):
        # Called inside asyncio.to_thread; keep it simple and thread-safe.
        self.calls.append(_Call(args=(), kwargs=dict(kwargs)))

        # "Hybrid" path passes fetch_k; simulate an exception to trigger dense fallback.
        if self.fail_hybrid and "fetch_k" in kwargs:
            raise RuntimeError("hybrid not supported")

        docs = [
            Document(page_content="d1", metadata={"parent_id": "p1"}),
            Document(page_content="d2", metadata={"parent_id": "p2"}),
        ]
        # Return (Document, score) pairs like LangChain expects.
        return [(docs[0], 0.8), (docs[1], 0.2)]


def test_intelligent_ranker_selection_keyword_vs_semantic():
    module = RetrievalOptimizationModule(vectorstore=FakeVectorStore())

    ranker_type, weights = module.intelligent_ranker_selection("如何 做 红烧肉")
    assert ranker_type == "weighted"
    assert weights == [0.4, 0.6]

    ranker_type, weights = module.intelligent_ranker_selection("推荐一些家常菜")
    assert ranker_type == "weighted"
    assert weights == [0.6, 0.4]

    ranker_type, weights = module.intelligent_ranker_selection("番茄炒蛋")
    assert ranker_type == "weighted"
    assert weights == [0.5, 0.5]


def test_hybrid_search_filters_by_threshold_when_supported():
    module = RetrievalOptimizationModule(
        vectorstore=FakeVectorStore(),
        score_threshold=0.0,
        default_ranker_type="weighted",
    )

    async def _run():
        docs, scores = await module.hybrid_search(
            query="query",
            top_k=2,
            ranker_type="weighted",
            ranker_weights=[0.5, 0.5],
            score_threshold=0.5,
        )
        return docs, scores

    docs, scores = asyncio.run(_run())
    assert [d.page_content for d in docs] == ["d1"]
    assert scores == [0.8]


def test_hybrid_search_falls_back_to_dense_and_skips_filtering():
    store = FakeVectorStore(fail_hybrid=True)
    module = RetrievalOptimizationModule(
        vectorstore=store,
        score_threshold=0.0,
        default_ranker_type="weighted",
    )

    async def _run():
        docs, scores = await module.hybrid_search(
            query="query",
            top_k=2,
            ranker_type="weighted",
            ranker_weights=[0.5, 0.5],
            score_threshold=0.5,  # would filter if hybrid succeeded
            expr='user_id == "u1"',
        )
        return docs, scores

    docs, scores = asyncio.run(_run())

    # Two attempts: hybrid attempt failed, then dense fallback.
    assert len(store.calls) == 2
    assert "fetch_k" in store.calls[0].kwargs
    assert "fetch_k" not in store.calls[1].kwargs

    # Dense fallback should return unfiltered results.
    assert [d.page_content for d in docs] == ["d1", "d2"]
    assert scores == [0.8, 0.2]

