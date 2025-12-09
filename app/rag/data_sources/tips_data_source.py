# app/rag/data_sources/tips_data_source.py
import logging
import uuid
from pathlib import Path
from typing import List, final

from langchain_text_splitters import MarkdownHeaderTextSplitter
from langchain_core.documents import Document

from app.rag.data_sources.base import BaseDataSource

logger = logging.getLogger(__name__)

# A specific namespace for generating document IDs
DOC_NAMESPACE = uuid.UUID('7a7de5f8-7435-4354-9b1b-d50a09848520')
MAX_K = 3  # Max number of parent documents to return after retrieval

class TipsDataSource(BaseDataSource):
    """
    Data source for loading and processing cooking tips from the HowToCook repository.
    """

    def __init__(self, data_path: str, headers_to_split_on: list):
        self.data_path = Path(data_path)
        self.headers_to_split_on = headers_to_split_on
        self.parent_doc_map: dict = {}
        self.parent_documents: List[Document] = []
        self.chunks: List[Document] = []

    def get_chunks(self) -> List[Document]:
        """
        Loads documents, processes them, and returns the final chunks for indexing.
        """
        logger.info(f"Loading and processing data from Tips source: {self.data_path}")
        self.parent_documents = self._load_parent_documents()
        self.parent_doc_map = {doc.id: doc for doc in self.parent_documents}
        self.chunks = self._create_child_chunks(self.parent_documents)
        
        logger.info(f"Processing complete. Found {len(self.parent_documents)} tip documents "
                    f"and created {len(self.chunks)} chunks.")
        return self.chunks

    def post_process_retrieval(self, retrieved_chunks: List[Document]) -> List[Document]:
        """
        Converts retrieved child chunks back to their full parent documents.
        Preserves the highest retrieval score from child chunks to parent documents.
        """
        if not self.parent_doc_map:
            logger.warning("Parent document map not loaded for Tips. Loading them now.")
            self.parent_documents = self._load_parent_documents()
            self.parent_doc_map = {doc.id: doc for doc in self.parent_documents}

        # Group chunks by parent_id and find the highest score for each parent
        parent_scores = {}
        for chunk in retrieved_chunks:
            parent_id = chunk.metadata.get("parent_id")
            if parent_id:
                score = chunk.metadata.get("retrieval_score", 0.0)
                if parent_id not in parent_scores or score > parent_scores[parent_id]:
                    parent_scores[parent_id] = score

        # Get parent documents and set their retrieval scores
        final_docs = []
        for parent_id, max_score in parent_scores.items():
            if parent_id in self.parent_doc_map:
                parent_doc = self.parent_doc_map[parent_id]
                # Create a copy to avoid modifying the original
                parent_doc = Document(
                    id=parent_doc.id,
                    page_content=parent_doc.page_content,
                    metadata=parent_doc.metadata.copy()
                )
                parent_doc.metadata['retrieval_score'] = max_score
                final_docs.append(parent_doc)
        # sort by retrieval score descending
        final_docs.sort(key=lambda d: d.metadata.get('retrieval_score', 0.0), reverse=True)
        # cut off to top k if needed
        final_docs = final_docs[:MAX_K]
        
        logger.info(f"Retrieved {len(retrieved_chunks)} tip chunks, corresponding to "
                    f"{len(final_docs)} unique parent tip documents.")
        return final_docs

    def _load_parent_documents(self) -> List[Document]:
        """Loads all markdown files as 'parent' documents."""
        documents = []
        for md_file in self.data_path.rglob("*.md"):
            try:
                with open(md_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Generate a deterministic ID based on the file path
                doc_id = str(uuid.uuid5(DOC_NAMESPACE, str(md_file)))
                doc = Document(
                    id=doc_id,
                    page_content=content,
                    metadata={
                        "source": str(md_file), 
                        "parent_id": None,
                        "title": md_file.stem,
                        "data_source": "tips"
                    }
                )
                documents.append(doc)
            except Exception as e:
                logger.warning(f"Failed to read tip file {md_file}: {e}")
        return documents

    def _create_child_chunks(self, parent_documents: List[Document]) -> List[Document]:
        """Splits documents into smaller chunks."""
        markdown_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=self.headers_to_split_on, strip_headers=False
        )
        all_chunks = []
        for doc in parent_documents:
            md_chunks = markdown_splitter.split_text(doc.page_content)
            for i, chunk in enumerate(md_chunks):
                chunk.id = str(uuid.uuid4())
                chunk.metadata.update(doc.metadata)
                chunk.metadata.update({
                    "parent_id": doc.id,
                    "chunk_index": i
                })
            all_chunks.extend(md_chunks)
        return all_chunks
