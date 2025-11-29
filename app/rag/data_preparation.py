# app/rag/data_preparation.py
import logging
from pathlib import Path
from typing import List, Dict, Any

from langchain_text_splitters import MarkdownHeaderTextSplitter
from langchain_core.documents import Document

from app.rag.data_sources.base import BaseDataSource

logger = logging.getLogger(__name__)

class DataPreparationModule:
    """
    Handles the common data processing steps of loading from a source and chunking.
    """
    def __init__(self, data_source: BaseDataSource, headers_to_split_on: list):
        """
        Args:
            data_source: An instance of a class that inherits from BaseDataSource.
            headers_to_split_on: Configuration for the Markdown splitter.
        """
        self.data_source = data_source
        self.headers_to_split_on = headers_to_split_on
        self.parent_documents: List[Document] = []
        self.child_chunks: List[Document] = []

    def run(self):
        """
        Main method to orchestrate the data preparation pipeline.
        """
        logger.info("Running data preparation pipeline...")
        self._load_documents_from_source()
        self._create_child_chunks()
        self._save_debug_files()
        logger.info(f"Data preparation complete. "
                    f"Processed {len(self.parent_documents)} parent documents "
                    f"and created {len(self.child_chunks)} child chunks.")

    def _load_documents_from_source(self):
        """Loads documents using the provided data source."""
        self.parent_documents = self.data_source.load_documents()

    def _create_child_chunks(self):
        """
        Splits parent documents into smaller 'child' chunks based on Markdown headers
        and ensures consistent metadata keys across all chunks.
        """
        if not self.parent_documents:
            raise ValueError("Parent documents must be loaded before creating chunks.")

        markdown_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=self.headers_to_split_on,
            strip_headers=False
        )

        all_chunks = []
        header_keys = [h[1] for h in self.headers_to_split_on]

        for doc in self.parent_documents:
            md_chunks = markdown_splitter.split_text(doc.page_content)
            
            for i, chunk in enumerate(md_chunks):
                chunk.metadata.update(doc.metadata)
                chunk.metadata.update({
                    "doc_type": "child",
                    "chunk_index": i
                })
                for key in header_keys:
                    if key not in chunk.metadata:
                        chunk.metadata[key] = ""
                
            all_chunks.extend(md_chunks)
        
        self.child_chunks = all_chunks

    def _save_debug_files(self):
        """Saves parent and child documents to jsonl files for debugging."""
        if not self.parent_documents and not self.child_chunks:
            logger.warning("No documents or chunks to save.")
            return
            
        debug_path = Path("data/debug")
        debug_path.mkdir(exist_ok=True)
        
        logger.info(f"Saving debug files to {debug_path}...")
        with open(debug_path / "parent_documents.jsonl", "w", encoding="utf-8") as f:
            for doc in self.parent_documents:
                f.write(doc.model_dump_json(exclude_unset=True) + "\n")
        with open(debug_path / "child_chunks.jsonl", "w", encoding="utf-8") as f:
            for chunk in self.child_chunks:
                f.write(chunk.model_dump_json(exclude_unset=True) + "\n")

    def get_statistics(self) -> Dict[str, Any]:
        """Returns statistics about the loaded data."""
        if not self.parent_documents:
            return {}
        
        categories = {}
        difficulties = {}
        for doc in self.parent_documents:
            cat = doc.metadata.get('category', '未知')
            diff = doc.metadata.get('difficulty', '未知')
            categories[cat] = categories.get(cat, 0) + 1
            difficulties[diff] = difficulties.get(diff, 0) + 1

        return {
            'total_parent_documents': len(self.parent_documents),
            'total_child_chunks': len(self.child_chunks),
            'categories': categories,
            'difficulties': difficulties
        }
