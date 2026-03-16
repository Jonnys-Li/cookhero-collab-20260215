from __future__ import annotations

import asyncio
from types import SimpleNamespace

from langchain_core.documents import Document

from app.services.rag_service import RAGService


class FakeCacheManager:
    def __init__(self, docs=None):
        self._docs = docs
        self.get_calls = []
        self.set_calls = []

    async def get(self, data_source: str, query: str, scope=None):
        self.get_calls.append((data_source, query, scope))
        return self._docs

    async def set(self, data_source: str, query: str, documents, scope=None):
        self.set_calls.append((data_source, query, scope, len(documents)))
        return True


class FakeRetrievalModule:
    def __init__(self, docs, scores):
        self.docs = docs
        self.scores = scores

    def intelligent_ranker_selection(self, _q: str):
        return "weighted", [0.5, 0.5]

    async def hybrid_search(self, _q: str, top_k: int, **_kwargs):
        _ = top_k
        return self.docs, self.scores


def test_build_filter_expr_scopes_personal_queries():
    assert RAGService._build_filter_expr("category == \"川菜\"", "recipes", None) == 'category == "川菜"'
    assert RAGService._build_filter_expr(None, "personal", "u1") == 'user_id == "u1"'
    assert (
        RAGService._build_filter_expr('category == "川菜"', "personal", "u1")
        == '(category == "川菜") and (user_id == "u1")'
    )


def test_extract_sources_deduplicates_by_info():
    service = RAGService.__new__(RAGService)
    docs = [
        Document(page_content="x", metadata={"dish_name": "A"}),
        Document(page_content="y", metadata={"dish_name": "A"}),
        Document(page_content="z", metadata={"category": "C"}),
    ]
    sources = service._extract_sources(docs)
    assert {"type": "rag", "info": "A"} in sources
    assert {"type": "rag", "info": "C"} in sources
    assert len(sources) == 2


def test_retrieve_from_source_uses_cache_and_sets_metadata():
    service = RAGService.__new__(RAGService)
    cached = [Document(page_content="x", metadata={})]
    service.cache_manager = FakeCacheManager(docs=cached)

    retrieval_module = FakeRetrievalModule([], [])

    async def _run():
        docs = await service._retrieve_from_source(
            source_name="personal",
            retrieval_module=retrieval_module,
            rewritten_query="q",
            top_k=3,
            use_intelligent_ranker=True,
            metadata_expression=None,
            user_id="u1",
        )
        assert len(docs) == 1
        assert docs[0].metadata["retrieval_score"] == 1.0
        assert docs[0].metadata["data_source"] == "personal"

    asyncio.run(_run())


def test_retrieve_from_source_deduplicates_and_caches_results():
    service = RAGService.__new__(RAGService)
    service.cache_manager = FakeCacheManager(docs=None)

    docs = [
        Document(page_content="a", metadata={"parent_id": "p1"}),
        Document(page_content="b", metadata={"parent_id": "p1"}),
        Document(page_content="c", metadata={"parent_id": "p2"}),
    ]
    scores = [0.1, 0.9, 0.2]
    retrieval_module = FakeRetrievalModule(docs, scores)

    async def _run():
        out = await service._retrieve_from_source(
            source_name="recipes",
            retrieval_module=retrieval_module,
            rewritten_query="q",
            top_k=3,
            use_intelligent_ranker=True,
            metadata_expression=None,
            user_id=None,
        )
        # p1 should keep the higher score doc ("b")
        assert [d.page_content for d in out] == ["b", "c"]
        assert service.cache_manager.set_calls

    asyncio.run(_run())

