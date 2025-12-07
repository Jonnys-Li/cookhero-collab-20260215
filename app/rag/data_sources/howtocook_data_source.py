# app/rag/data_sources/howtocook_data_source.py
import logging
from math import log
import uuid
from pathlib import Path
from typing import List, Tuple, Dict, Any

from langchain_text_splitters import MarkdownHeaderTextSplitter
from langchain_core.documents import Document

from app.rag.data_sources.base import BaseDataSource

logger = logging.getLogger(__name__)

# A specific namespace for generating document IDs
DOC_NAMESPACE = uuid.UUID('7a7de5f8-7435-4354-9b1b-d50a09848520')

class HowToCookDataSource(BaseDataSource):
    """
    Data source for loading and processing recipes from the HowToCook repository.
    """
    CATEGORY_MAPPING = {
        'meat_dish': '荤菜',
        'vegetable_dish': '素菜',
        'soup': '汤品',
        'dessert': '甜品',
        'breakfast': '早餐',
        'staple': '主食',
        'aquatic': '水产',
        'condiment': '调料',
        'drink': '饮品',
        'semi-finished': '半成品',
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
        self.parent_doc_map = {doc.id: doc for doc in self.parent_documents}
        self.chunks = self._create_child_chunks(self.parent_documents)
        
        self._save_debug_files(self.parent_documents, self.chunks)
        
        logger.info(f"Processing complete. Found {len(self.parent_documents)} documents "
                    f"and created {len(self.chunks)} chunks.")
        return self.chunks

    def post_process_retrieval(self, retrieved_chunks: List[Document]) -> List[Document]:
        """
        Converts retrieved child chunks back to their full parent documents.
        This implements the "small to large" retrieval pattern.
        Preserves the highest retrieval score from child chunks to parent documents.
        Special handling for dish index chunks: returns the index document as-is.
        """
        if not self.parent_doc_map:
            logger.warning("Parent document map not loaded for Tips. Loading them now.")
            self.parent_documents = self._load_parent_documents()
            self.parent_doc_map = {doc.id: doc for doc in self.parent_documents}

        # Check if any retrieved chunks are from the dish index
        index_chunks = [chunk for chunk in retrieved_chunks if chunk.metadata.get("is_dish_index", False)]
        regular_chunks = [chunk for chunk in retrieved_chunks if not chunk.metadata.get("is_dish_index", False)]
        
        final_docs = []
        
        # Handle dish index chunks separately - return the index document as-is
        if index_chunks:
            # Get the highest score from index chunks
            max_index_score = max(
                (chunk.metadata.get("retrieval_score", 0.0) for chunk in index_chunks),
                default=0.0
            )
            # Find the index document
            index_doc_id = index_chunks[0].metadata.get("parent_id")
            if index_doc_id and index_doc_id in self.parent_doc_map:
                index_doc = self.parent_doc_map[index_doc_id]
                # Create a copy with the score
                index_doc_copy = Document(
                    id=index_doc.id,
                    page_content=index_doc.page_content,
                    metadata=index_doc.metadata.copy()
                )
                index_doc_copy.metadata['retrieval_score'] = max_index_score
                final_docs.append(index_doc_copy)
                logger.info(f"Retrieved dish index document with score {max_index_score:.4f}")

        # Handle regular chunks: group by parent_id and find the highest score for each parent
        parent_scores = {}
        for chunk in regular_chunks:
            parent_id = chunk.metadata.get("parent_id")
            if parent_id:
                score = chunk.metadata.get("retrieval_score", 0.0)
                if parent_id not in parent_scores or score > parent_scores[parent_id]:
                    parent_scores[parent_id] = score

        # Get parent documents and set their retrieval scores
        for parent_id, max_score in parent_scores.items():
            if parent_id in self.parent_doc_map:
                parent_doc = self.parent_doc_map[parent_id]
                # Skip the index document if we already added it
                if parent_doc.metadata.get("is_dish_index", False):
                    continue
                # Create a copy to avoid modifying the original
                parent_doc = Document(
                    id=parent_doc.id,
                    page_content=parent_doc.page_content,
                    metadata=parent_doc.metadata.copy()
                )
                parent_doc.metadata['retrieval_score'] = max_score
                final_docs.append(parent_doc)
        
        logger.info(f"Retrieved {len(retrieved_chunks)} chunks ({len(index_chunks)} index, {len(regular_chunks)} regular), "
                    f"corresponding to {len(final_docs)} unique parent documents.")
        return final_docs

    def _load_parent_documents(self) -> List[Document]:
        """Loads all markdown files as 'parent' documents."""
        documents = []
        # Collect dish information for the index document
        dishes_by_category: Dict[str, List[str]] = {}
        
        for md_file in self.data_path.rglob("*.md"):
            try:
                with open(md_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Generate a deterministic ID based on the file path
                doc_id = str(uuid.uuid5(DOC_NAMESPACE, str(md_file)))
                doc = Document(
                    id=doc_id,
                    page_content=content,
                    metadata={"source": str(md_file), "parent_id": None}
                )
                self._enhance_metadata(doc)
                documents.append(doc)
                
                # Collect dish name and category for index
                dish_name = doc.metadata.get('dish_name', md_file.stem)
                category = doc.metadata.get('category', '其他')
                if category not in dishes_by_category:
                    dishes_by_category[category] = []
                dishes_by_category[category].append(dish_name)
            except Exception as e:
                logger.warning(f"Failed to read file {md_file}: {e}")
        
        # Create a dish index document containing all dish names organized by category
        index_doc = self._create_dish_index_document(dishes_by_category)
        if index_doc:
            documents.append(index_doc)
            logger.info(f"Created dish index document with {sum(len(dishes) for dishes in dishes_by_category.values())} dishes across {len(dishes_by_category)} categories")
        
        return documents
    
    def _create_dish_index_document(self, dishes_by_category: Dict[str, List[str]]) -> Document:
        """
        Creates a special index document containing all dish names organized by category.
        This document will be used for recommendation queries.
        """
        if not dishes_by_category:
            return None
        
        # Build the index content
        content_parts = ["# 菜谱索引\n\n"]
        content_parts.append("本索引包含所有可用的菜谱名称，按类别组织。\n\n")
        
        # Add dishes by category
        for category in sorted(dishes_by_category.keys()):
            dishes = sorted(dishes_by_category[category])
            content_parts.append(f"## {category}\n\n")
            content_parts.append("推荐菜，菜谱列表，")
            content_parts.append(f"{category}推荐：")
            content_parts.append("、".join(dishes))
            content_parts.append("\n\n")
        
        # Add a summary section
        content_parts.append("## 所有菜谱\n\n")
        all_dishes = []
        for dishes in dishes_by_category.values():
            all_dishes.extend(dishes)
        content_parts.append("推荐菜，菜谱列表，所有菜谱：")
        content_parts.append("、".join(sorted(all_dishes)))
        content_parts.append("\n")
        
        index_content = "".join(content_parts)
        
        # Generate a special ID for the index document
        index_id = str(uuid.uuid5(DOC_NAMESPACE, "dish_index"))
        
        index_doc = Document(
            id=index_id,
            page_content=index_content,
            metadata={
                "source": "dish_index",
                "parent_id": None,
                "dish_name": "菜谱索引",
                "category": "索引",
                "is_dish_index": True,  # Special flag to identify this document
                "total_dishes": sum(len(dishes) for dishes in dishes_by_category.values()),
                "categories": list(dishes_by_category.keys())
            }
        )
        
        return index_doc

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
            # Check if this is the dish index document - create a special chunk
            if doc.metadata.get("is_dish_index", False):
                # Create a chunk with only recommendation-related keywords (no dish names)
                # This makes it easier to match "recommendation" queries semantically
                chunk_content = self._create_index_chunk_content(doc.metadata)
                index_chunk = Document(
                    id=str(uuid.uuid4()),
                    page_content=chunk_content,
                    metadata=doc.metadata.copy()
                )
                index_chunk.metadata.update({
                    "parent_id": doc.id,
                    "chunk_index": 0,
                    "is_dish_index": True
                })
                all_chunks.append(index_chunk)
                logger.info("Created recommendation-focused chunk for dish index document")
            else:
                # Regular documents: split into chunks
                md_chunks = markdown_splitter.split_text(doc.page_content)
                for i, chunk in enumerate(md_chunks):
                    chunk.id = str(uuid.uuid4())
                    chunk.metadata.update(doc.metadata)
                    chunk.metadata.update({
                        "parent_id": doc.id,
                        "chunk_index": i
                        })
                    for key in header_keys:
                        if key not in chunk.metadata:
                            chunk.metadata[key] = ""
                all_chunks.extend(md_chunks)
        return all_chunks
    
    def _create_index_chunk_content(self, index_metadata: Dict[str, Any]) -> str:
        """
        Creates chunk content for the dish index that focuses on recommendation keywords
        without including actual dish names. This improves semantic matching for 
        recommendation queries.
        """
        categories = index_metadata.get("categories", [])
        total_dishes = index_metadata.get("total_dishes", 0)
        
        content_parts = []
        content_parts.append("推荐菜，菜谱列表，")
        
        # Add category-specific recommendation keywords
        for category in sorted(categories):
            content_parts.append(f"{category}推荐，")
        
        # Add general recommendation keywords
        content_parts.append("家常菜推荐，")
        content_parts.append("菜品推荐，")
        content_parts.append("食谱推荐，")
        content_parts.append(f"共有{total_dishes}道菜谱可供推荐")
        
        return "".join(content_parts)

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
