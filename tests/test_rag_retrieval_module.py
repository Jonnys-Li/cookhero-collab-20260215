from __future__ import annotations

import asyncio

from langchain_core.documents import Document

from app.rag.pipeline.retrieval import RetrievalOptimizationModule


class FakeVectorStore:
    def __init__(self, *, fail_hybrid: bool = False):
        self.fail_hybrid = fail_hybrid
        self.calls = []

    def similarity_search_with_score(self, *, query: str, k: int, expr=None, **kwargs):
        self.calls.append({"query": query, "k": k, "expr": expr, "kwargs": kwargs})
        if self.fail_hybrid and "ranker_type" in kwargs:
            raise RuntimeError("hybrid not supported")
        docs = [
            Document(page_content="a", metadata={"parent_id": "p1"}),
            Document(page_content="b", metadata={"parent_id": "p2"}),
        ]
        scores = [0.9, 0.1]
        return list(zip(docs, scores))


def test_intelligent_ranker_selection_keyword_and_semantic_and_default():
    vs = FakeVectorStore()
    module = RetrievalOptimizationModule(vectorstore=vs)

    t1, w1 = module.intelligent_ranker_selection("红烧肉怎么做")
    assert t1 == "weighted"
    assert w1 == [0.4, 0.6]

    t2, w2 = module.intelligent_ranker_selection("推荐一些家常菜")
    assert t2 == "weighted"
    assert w2 == [0.6, 0.4]

    t3, w3 = module.intelligent_ranker_selection("hello")
    assert t3 == "weighted"
    assert w3 == [0.5, 0.5]


def test_hybrid_search_filters_by_threshold_when_supported():
    vs = FakeVectorStore()
    module = RetrievalOptimizationModule(vectorstore=vs)

    async def _run():
        docs, scores = await module.hybrid_search(
            query="q",
            top_k=2,
            ranker_type="weighted",
            ranker_weights=[0.5, 0.5],
            score_threshold=0.5,
        )
        assert [d.page_content for d in docs] == ["a"]
        assert scores == [0.9]

    asyncio.run(_run())


def test_hybrid_search_falls_back_to_dense_when_hybrid_fails():
    vs = FakeVectorStore(fail_hybrid=True)
    module = RetrievalOptimizationModule(vectorstore=vs)

    async def _run():
        docs, scores = await module.hybrid_search(
            query="q",
            top_k=2,
            ranker_type="weighted",
            score_threshold=0.5,
        )
        # Dense fallback should not filter.
        assert [d.page_content for d in docs] == ["a", "b"]
        assert scores == [0.9, 0.1]

    asyncio.run(_run())

