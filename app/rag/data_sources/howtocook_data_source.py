# app/rag/data_sources/howtocook_data_source.py
import logging
import hashlib
from pathlib import Path
from typing import List, Dict, Any
from langchain_core.documents import Document

from app.rag.data_sources.base import BaseDataSource

logger = logging.getLogger(__name__)

class HowToCookDataSource(BaseDataSource):
    """
    Data source for loading recipes from the HowToCook markdown repository.
    """
    # Static mappings for consistency across the application
    CATEGORY_MAPPING = {
        'meat_dish': '荤菜', 'vegetable_dish': '素菜', 'soup': '汤品',
        'dessert': '甜品', 'breakfast': '早餐', 'staple': '主食',
        'aquatic': '水产', 'condiment': '调料', 'drink': '饮品'
    }
    DIFFICULTY_LABELS = ['非常简单', '简单', '中等', '困难', '非常困难']

    def __init__(self, data_path: str):
        """
        Args:
            data_path: The path to the HowToCook data directory.
        """
        self.data_path = Path(data_path)

    def load_documents(self) -> List[Document]:
        """
        Loads all markdown files as documents and enriches their metadata.
        """
        logger.info(f"Loading documents from HowToCook source: {self.data_path}")
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
        
        logger.info(f"Successfully loaded {len(documents)} documents from HowToCook source.")
        return documents

    def _enhance_metadata(self, doc: Document):
        """
        Enriches a document with metadata based on its path and content.
        """
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
