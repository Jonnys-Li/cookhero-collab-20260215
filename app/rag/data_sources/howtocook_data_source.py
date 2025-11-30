# app/rag/data_sources/howtocook_data_source.py
import logging
import hashlib
from pathlib import Path
from typing import List

from anyio import sleep_forever
from langchain_text_splitters import MarkdownHeaderTextSplitter
from langchain_core.documents import Document

from app.rag.data_sources.base import BaseDataSource

logger = logging.getLogger(__name__)

class HowToCookDataSource(BaseDataSource):
    """
    Data source for loading and processing recipes from the HowToCook repository.
    """
    CATEGORY_MAPPING = {
        'meat_dish': '荤菜', 'vegetable_dish': '素菜', 'soup': '汤品',
        'dessert': '甜品', 'breakfast': '早餐', 'staple': '主食',
        'aquatic': '水产', 'condiment': '调料', 'drink': '饮品'
    }

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
        logger.info(f"Loading and processing data from HowToCook source: {self.data_path}")
        self.parent_documents = self._load_parent_documents()
        # Create a mapping of parent_id to parent_document for quick lookup
        self.parent_doc_map = {doc.metadata["parent_id"]: doc for doc in self.parent_documents}
        self.chunks = self._create_child_chunks(self.parent_documents)
        
        self._save_debug_files(self.parent_documents, self.chunks)
        
        logger.info(f"Processing complete. Found {len(self.parent_documents)} documents "
                    f"and created {len(self.chunks)} chunks.")
        return self.chunks

    def post_process_retrieval(self, retrieved_chunks: List[Document]) -> List[Document]:
        """
        Converts retrieved child chunks back to their full parent documents.
        This implements the "small to large" retrieval pattern.
        """
        if not self.parent_documents:
            logger.warning("Parent documents not loaded. Loading them now for post-processing.")
            self.parent_documents = self._load_parent_documents()
        
        logger.info(f"retrieved_chunks metadata: {[doc.metadata for doc in retrieved_chunks]}")

        parent_ids = set()
        for chunk in retrieved_chunks:
            parent_id = chunk.metadata.get("parent_id")
            if parent_id:
                parent_ids.add(parent_id)

        # Retrieve the unique parent documents
        final_docs = [self.parent_doc_map[pid] for pid in parent_ids if pid in self.parent_doc_map]
        
        logger.info(f"Retrieved {len(retrieved_chunks)} chunks, which correspond to "
                    f"{len(final_docs)} unique parent documents.")
        logger.info(f"Final documents metadata: {[doc.metadata for doc in final_docs]}")
        return final_docs

    def _load_parent_documents(self) -> List[Document]:
        """Loads all markdown files as 'parent' documents."""
        documents = []
        for md_file in self.data_path.rglob("*.md"):
            try:
                with open(md_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                relative_path = md_file.relative_to(self.data_path.parent).as_posix()
                parent_id = hashlib.md5(relative_path.encode("utf-8")).hexdigest()
                doc = Document(
                    page_content=content,
                    metadata={"source": str(md_file), "parent_id": parent_id}
                )
                self._enhance_metadata(doc)
                documents.append(doc)
            except Exception as e:
                logger.warning(f"Failed to read file {md_file}: {e}")
        return documents

    def _enhance_metadata(self, doc: Document):
        """Enriches a document with metadata."""
        file_path = Path(doc.metadata.get('source', ''))
        path_parts = file_path.parts
        
        doc.metadata['category'] = '其他'
        for key, value in self.CATEGORY_MAPPING.items():
            if key in path_parts:
                doc.metadata['category'] = value
                break
        
        doc.metadata['dish_name'] = file_path.stem

        content = doc.page_content
        if '★★★★★' in content: doc.metadata['difficulty'] = '非常困难'
        elif '★★★★' in content: doc.metadata['difficulty'] = '困难'
        elif '★★★' in content: doc.metadata['difficulty'] = '中等'
        elif '★★' in content: doc.metadata['difficulty'] = '简单'
        elif '★' in content: doc.metadata['difficulty'] = '非常简单'
        else: doc.metadata['difficulty'] = '未知'

    def _create_child_chunks(self, parent_documents: List[Document]) -> List[Document]:
        """Splits documents into smaller chunks."""
        markdown_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=self.headers_to_split_on, strip_headers=False
        )
        all_chunks = []
        header_keys = [h[1] for h in self.headers_to_split_on]

        for doc in parent_documents:
            md_chunks = markdown_splitter.split_text(doc.page_content)
            for i, chunk in enumerate(md_chunks):
                chunk.metadata.update(doc.metadata)
                chunk.metadata.update({"doc_type": "child", "chunk_index": i})
                for key in header_keys:
                    if key not in chunk.metadata:
                        chunk.metadata[key] = ""
            all_chunks.extend(md_chunks)
        return all_chunks

    def _save_debug_files(self, parent_docs: List[Document], child_chunks: List[Document]):
        """Saves documents to jsonl files for debugging."""
        debug_path = Path("data/debug")
        debug_path.mkdir(exist_ok=True)
        
        logger.info(f"Saving debug files to {debug_path}...")
        with open(debug_path / "parent_documents.jsonl", "w", encoding="utf-8") as f:
            for doc in parent_docs:
                f.write(doc.model_dump_json(exclude_unset=True) + "\n")
        with open(debug_path / "child_chunks.jsonl", "w", encoding="utf-8") as f:
            for chunk in child_chunks:
                f.write(chunk.model_dump_json(exclude_unset=True) + "\n")
