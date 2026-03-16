from __future__ import annotations

import asyncio
from types import SimpleNamespace

from langchain_core.documents import Document

from app.rag.pipeline.document_processor import DocumentProcessor


def test_document_processor_create_chunks_sets_parent_id_and_required_keys():
    processor = DocumentProcessor(headers_to_split_on=[("#", "h1"), ("##", "h2")])
    base_meta = {
        "source": "recipes::1",
        "parent_id": "should-be-overridden",
        "dish_name": "Mapo tofu",
        "category": "川菜",
        "difficulty": "easy",
        "is_dish_index": False,
        "data_source": "recipes",
        "user_id": None,
        "source_type": "recipes",
    }

    chunks = processor.create_chunks(
        doc_id="parent-1",
        content="# Title\n\nhello\n\n## Steps\n\n1. a\n",
        metadata=base_meta,
    )
    assert chunks
    assert all(c.metadata.get("parent_id") == "parent-1" for c in chunks)
    assert all("dish_name" in c.metadata for c in chunks)


def test_document_processor_post_process_retrieval_fetches_parents_and_sorts(monkeypatch):
    processor = DocumentProcessor(headers_to_split_on=[("#", "h1")])

    parent_id = "p1"
    retrieved = [
        Document(
            id="c1",
            page_content="chunk1",
            metadata={"parent_id": parent_id, "retrieval_score": 0.2, "rerank_score": 0.5},
        ),
        Document(
            id="c2",
            page_content="chunk2",
            metadata={"parent_id": parent_id, "retrieval_score": 0.9, "rerank_score": 0.4},
        ),
        Document(id="c3", page_content="no-parent", metadata={}),
    ]

    async def fake_get_parent_documents(ids):
        assert parent_id in ids
        return {
            parent_id: Document(
                id=parent_id,
                page_content="FULL",
                metadata={"dish_name": "Mapo tofu", "category": "川菜"},
            )
        }

    from app.rag.pipeline import document_processor as module

    monkeypatch.setattr(module.document_repository, "get_parent_documents", fake_get_parent_documents)

    async def _run():
        docs = await processor.post_process_retrieval(retrieved)
        assert len(docs) == 1
        doc = docs[0]
        assert doc.page_content == "FULL"
        assert doc.metadata["retrieval_score"] == 0.9
        assert doc.metadata["rerank_score"] == 0.5

    asyncio.run(_run())


def test_document_processor_create_index_chunk_content_variants():
    processor = DocumentProcessor()
    s1 = processor._create_index_chunk_content(
        {"source": "category::x", "category": "川菜", "difficulty": ""}
    )
    assert "川菜" in s1

    s2 = processor._create_index_chunk_content(
        {"source": "difficulty::x", "category": "", "difficulty": "easy"}
    )
    assert "easy" in s2

