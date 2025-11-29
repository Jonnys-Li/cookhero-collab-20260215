# app/rag/data_preparation.py
import logging
import hashlib
from pathlib import Path
from typing import List, Dict, Any

from langchain_text_splitters import MarkdownHeaderTextSplitter
from langchain_core.documents import Document

logger = logging.getLogger(__name__)

class DataPreparationModule:
    """
    Handles loading, cleaning, and preprocessing of recipe data.
    """
    # Static mappings for consistency across the application
    CATEGORY_MAPPING = {
        'meat_dish': '荤菜', 'vegetable_dish': '素菜', 'soup': '汤品',
        'dessert': '甜品', 'breakfast': '早餐', 'staple': '主食',
        'aquatic': '水产', 'condiment': '调料', 'drink': '饮品'
    }
    DIFFICULTY_LABELS = ['非常简单', '简单', '中等', '困难', '非常困难']

    def __init__(self, data_path: str, headers_to_split_on: list):
        """
        Initializes the data preparation module.
        Args:
            data_path: The path to the data directory.
            headers_to_split_on: Configuration for the Markdown splitter.
        """
        self.data_path = Path(data_path)
        self.headers_to_split_on = headers_to_split_on
        self.parent_documents: List[Document] = []
        self.child_chunks: List[Document] = []

    def load_and_process_documents(self):
        """
        Main method to orchestrate the loading and processing of documents.
        """
        logger.info("Starting document loading and processing...")
        self._load_parent_documents()
        self._create_child_chunks()
        logger.info(f"Successfully processed {len(self.parent_documents)} parent documents "
                    f"and created {len(self.child_chunks)} child chunks.")

    def _load_parent_documents(self):
        """
        Loads all markdown files as 'parent' documents and enriches their metadata.
        """
        logger.info(f"Loading documents from: {self.data_path}")
        documents = []
        for md_file in self.data_path.rglob("*.md"):
            try:
                with open(md_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Generate a deterministic unique ID based on the file's relative path
                relative_path = md_file.relative_to(self.data_path.parent).as_posix()
                parent_id = hashlib.md5(relative_path.encode("utf-8")).hexdigest()

                doc = Document(
                    page_content=content,
                    metadata={
                        "source": str(md_file),
                        "parent_id": parent_id,
                        "doc_type": "parent"
                    }
                )
                self._enhance_metadata(doc)
                documents.append(doc)
            except Exception as e:
                logger.warning(f"Failed to read or process file {md_file}: {e}")
        
        self.parent_documents = documents

    def _enhance_metadata(self, doc: Document):
        """
        Enriches a document with metadata based on its path and content.
        """
        file_path = Path(doc.metadata.get('source', ''))
        path_parts = file_path.parts
        
        # Extract category
        doc.metadata['category'] = '其他'
        for key, value in self.CATEGORY_MAPPING.items():
            if key in path_parts:
                doc.metadata['category'] = value
                break
        
        # Extract dish name from filename
        doc.metadata['dish_name'] = file_path.stem

        # Extract difficulty from content
        content = doc.page_content
        if '★★★★★' in content: doc.metadata['difficulty'] = '非常困难'
        elif '★★★★' in content: doc.metadata['difficulty'] = '困难'
        elif '★★★' in content: doc.metadata['difficulty'] = '中等'
        elif '★★' in content: doc.metadata['difficulty'] = '简单'
        elif '★' in content: doc.metadata['difficulty'] = '非常简单'
        else: doc.metadata['difficulty'] = '未知'

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
                # Inherit metadata from parent
                chunk.metadata.update(doc.metadata)
                # Add child-specific metadata
                chunk.metadata.update({
                    "doc_type": "child",
                    "chunk_index": i
                })
                
                # Ensure all possible header keys are present to prevent schema mismatch
                for key in header_keys:
                    if key not in chunk.metadata:
                        chunk.metadata[key] = "" # Use empty string for missing headers
                
            all_chunks.extend(md_chunks)
        
        self.child_chunks = all_chunks

    def get_statistics(self) -> Dict[str, Any]:
        """Returns statistics about the loaded data."""
        if not self.parent_documents:
            return {}
        
        # save the document and chunks into jsonl files
        with open("data/documents/parent_documents.jsonl", "w", encoding="utf-8") as f:
            for doc in self.parent_documents:
                f.write(doc.model_dump_json() + "\n")
        with open("data/documents/child_chunks.jsonl", "w", encoding="utf-8") as f:
            for chunk in self.child_chunks:
                f.write(chunk.model_dump_json() + "\n")

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
