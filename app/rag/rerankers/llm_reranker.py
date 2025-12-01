# app/rag/rerankers/llm_reranker.py
import logging
from typing import List
from langchain_classic.retrievers.document_compressors import LLMChainFilter
from langchain_core.documents import Document
from langchain_openai import ChatOpenAI

from app.core.rag_config import RerankerConfig

logger = logging.getLogger(__name__)

class LLMReranker:
    """
    A reranker that uses an LLM to filter documents based on their relevance to a query.
    """

    def __init__(self, reranker_config: RerankerConfig):
        """
        Initializes the LLM Reranker.
        Args:
            reranker_config: The configuration for the reranker.
        """
        self.config = reranker_config
        self.llm = self._init_llm()
        self.filter = LLMChainFilter.from_llm(self.llm)

    def _init_llm(self) -> ChatOpenAI:
        """Initializes the Chat LLM for reranking."""
        logger.info(f"Initializing Reranker LLM: {self.config.model_name}")
        return ChatOpenAI(
            model=self.config.model_name,
            temperature=self.config.temperature,
            api_key=self.config.api_key, # type: ignore
            base_url=self.config.base_url or None
        )

    def rerank(self, query: str, documents: List[Document]) -> List[Document]:
        """
        Filters documents using the LLMChainFilter.

        Args:
            query: The user's query.
            documents: The list of documents to rerank/filter.

        Returns:
            A filtered list of documents deemed relevant by the LLM.
        """
        if not self.config.enabled:
            return documents
        
        if not documents:
            return []

        logger.info(f"Reranking {len(documents)} documents with LLM...")
        
        # The LLMChainFilter's default prompt asks the LLM to determine if the document
        # is relevant for the given query and expects a "YES" or "NO" answer.
        # We can use it directly.
        filtered_docs = self.filter.compress_documents(
            documents=documents,
            query=query
        )

        logger.info(f"Reranking complete. {len(documents)} -> {len(filtered_docs)} documents.")
        
        # Log which documents were filtered out
        original_doc_ids = {doc.metadata.get('source') for doc in documents}
        filtered_doc_ids = {doc.metadata.get('source') for doc in filtered_docs}
        discarded_docs = original_doc_ids - filtered_doc_ids
        if discarded_docs:
            logger.info(f"Discarded {len(discarded_docs)} documents: {discarded_docs}")
            
        return filtered_docs

