from __future__ import annotations

import asyncio

import pytest
from langchain_core.documents import Document

from app.rag.pipeline.document_processor import (
    DocumentProcessor,
    REQUIRED_METADATA_KEYS,
    document_processor,
)


def test_create_chunks_clones_required_metadata_and_sets_parent_id():
    processor = DocumentProcessor()
    metadata = {key: f"v_{key}" for key in REQUIRED_METADATA_KEYS}
    doc_id = "parent-1"

    chunks = processor.create_chunks(
        doc_id=doc_id,
        content="# Title\n\nSome content\n\n## Section\n\nMore content",
        metadata=metadata,
    )

    assert chunks, "Expected markdown splitter to produce at least one chunk"
    for chunk in chunks:
        assert chunk.id, "Chunk id should be populated"
        assert chunk.metadata.get("parent_id") == doc_id
        for key in REQUIRED_METADATA_KEYS:
            if key == "parent_id":
                # create_chunks explicitly overwrites parent_id to the passed doc_id.
                assert chunk.metadata.get(key) == doc_id
            else:
                assert chunk.metadata.get(key) == metadata[key]


def test_post_process_retrieval_groups_by_parent_and_preserves_best_scores(monkeypatch):
    # Prepare chunks for two parents; parent A has a better rerank_score.
    retrieved_chunks = [
        Document(
            id="c1",
            page_content="chunk A1",
            metadata={"parent_id": "A", "retrieval_score": 0.1, "rerank_score": 0.2},
        ),
        Document(
            id="c2",
            page_content="chunk A2",
            metadata={"parent_id": "A", "retrieval_score": 0.9},  # best retrieval
        ),
        Document(
            id="c3",
            page_content="chunk B1",
            metadata={"parent_id": "B", "retrieval_score": 0.8, "rerank_score": 0.1},
        ),
    ]

    async def fake_get_parent_documents(parent_ids: list[str]):
        assert set(parent_ids) == {"A", "B"}
        return {
            "A": Document(id="A", page_content="FULL A", metadata={"dish_name": "a"}),
            "B": Document(id="B", page_content="FULL B", metadata={"dish_name": "b"}),
        }

    monkeypatch.setattr(
        "app.rag.pipeline.document_processor.document_repository.get_parent_documents",
        fake_get_parent_documents,
    )

    async def _run():
        return await document_processor.post_process_retrieval(retrieved_chunks)

    parents = asyncio.run(_run())
    assert [d.id for d in parents] == ["A", "B"]

    # Scores should be propagated from chunk aggregation.
    doc_a = parents[0]
    assert doc_a.page_content == "FULL A"
    assert doc_a.metadata.get("retrieval_score") == 0.9
    assert doc_a.metadata.get("rerank_score") == 0.2


def test_post_process_retrieval_skips_missing_parent(monkeypatch, caplog):
    retrieved_chunks = [
        Document(
            id="c1",
            page_content="chunk missing",
            metadata={"parent_id": "MISSING", "retrieval_score": 0.5},
        )
    ]

    async def fake_get_parent_documents(_parent_ids: list[str]):
        return {}

    monkeypatch.setattr(
        "app.rag.pipeline.document_processor.document_repository.get_parent_documents",
        fake_get_parent_documents,
    )

    async def _run():
        return await document_processor.post_process_retrieval(retrieved_chunks)

    with caplog.at_level("WARNING"):
        parents = asyncio.run(_run())

    assert parents == []
    assert any("Parent document not found" in rec.message for rec in caplog.records)


@pytest.mark.parametrize(
    ("source", "category", "difficulty", "expected_fragment"),
    [
        ("category::foo", "家常菜", "", "家常菜推荐"),
        ("difficulty::foo", "", "简单", "简单难度推荐"),
    ],
)
def test_create_index_chunk_content_includes_signal(source, category, difficulty, expected_fragment):
    processor = DocumentProcessor()
    content = processor._create_index_chunk_content(
        {
            "source": source,
            "category": category,
            "difficulty": difficulty,
        }
    )
    assert expected_fragment in content
