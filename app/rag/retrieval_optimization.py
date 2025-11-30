# app/rag/retrieval_optimization.py
import hashlib
import logging
from math import log
from typing import List, Dict, Any

from langchain_milvus import Milvus
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document

logger = logging.getLogger(__name__)

class RetrievalOptimizationModule:
    """
    Handles advanced retrieval strategies like hybrid search and re-ranking.
    """
    def __init__(self, vectorstore: Milvus, child_chunks: List[Document]):
        """
        Initializes the retrieval optimization module.
        Args:
            vectorstore: The FAISS vectorstore containing the document chunks.
            child_chunks: The list of all child document chunks, used for BM25.
        """
        if not vectorstore or not child_chunks:
            raise ValueError("Vectorstore and child_chunks must be provided.")
            
        self.vectorstore = vectorstore
        self.child_chunks = child_chunks
        self._setup_retrievers()

    def _setup_retrievers(self):
        """Sets up the individual retrievers (vector and BM25)."""
        logger.info("Setting up retrievers...")
        # Vector retriever for semantic search
        self.vector_retriever = self.vectorstore.as_retriever(search_kwargs={"k": 10})
        
        # BM25 retriever for keyword-based search
        self.bm25_retriever = BM25Retriever.from_documents(
            self.child_chunks,
            k=10
        )
        logger.info("Vector and BM25 retrievers are ready.")
        
    def hybrid_search(self, query: str, top_k: int) -> List[Document]:
        """
        Performs a hybrid search by combining vector and BM25 results with RRF.
        Args:
            query: The user's search query.
            top_k: The final number of documents to return.
        Returns:
            A list of re-ranked documents.
        """
        # Get results from both retrievers
        vector_docs = self.vector_retriever.invoke(query)
        bm25_docs = self.bm25_retriever.invoke(query)

        logger.info(f"length of vector_docs: {len(vector_docs)}")
        logger.info(f"length of bm25_docs: {len(bm25_docs)}")

        for doc in vector_docs:
            logger.info("=" * 40)
            logger.info(f"vector_docs doc ID: {doc.id}, Metadata: {doc.metadata}")
        for doc in bm25_docs:
            logger.info("=" * 40)
            logger.info(f"bm25_docs doc ID: {doc.id}, Metadata: {doc.metadata}")

        # Re-rank using Reciprocal Rank Fusion (RRF)
        reranked_docs = self._reciprocal_rank_fusion([vector_docs, bm25_docs])
        
        return reranked_docs[:top_k]

    def metadata_filtered_search(self, query: str, filters: Dict[str, Any], top_k: int) -> List[Document]:
        """
        Performs a search and then applies metadata filters to the results.
        Note: This is a post-filtering approach. For large-scale systems, pre-filtering
        or using a vector store that supports metadata filtering natively is more efficient.
        
        Args:
            query: The user's search query.
            filters: A dictionary of metadata key-value pairs to filter on.
            top_k: The final number of documents to return.
            
        Returns:
            A list of filtered and re-ranked documents.
        """
        # Get a larger pool of candidates with hybrid search
        initial_candidates = self.hybrid_search(query, top_k * 5)
        
        # Apply filters
        filtered_docs = []
        for doc in initial_candidates:
            is_match = all(
                doc.metadata.get(key) == value for key, value in filters.items()
            )
            if is_match:
                filtered_docs.append(doc)
        
        logger.info(f"Found {len(filtered_docs)} documents matching filters out of "
                    f"{len(initial_candidates)} initial candidates.")
        
        return filtered_docs[:top_k]

    def _reciprocal_rank_fusion(self, result_sets: List[List[Document]], k: int = 60) -> List[Document]:
        """
        Performs Reciprocal Rank Fusion on a list of ranked document lists.
        Args:
            result_sets: A list where each element is a ranked list of Documents.
            k: A constant used in the RRF formula to smooth scores.
        Returns:
            A single, re-ranked list of unique documents.
        """
        # Dictionary to store the RRF scores for each document
        fused_scores = {}
        # Dictionary to store the actual Document objects, keyed by content hash
        doc_store = {}

        for docs in result_sets:
            for rank, doc in enumerate(docs):
                doc_id = doc.id
                doc_store[doc_id] = doc
                
                # RRF formula: 1 / (k + rank)
                score = 1.0 / (k + rank + 1)
                
                # Add the score to the document's fused score
                if doc_id not in fused_scores:
                    fused_scores[doc_id] = 0
                fused_scores[doc_id] += score

        # Sort documents based on their final fused scores in descending order
        reranked_results = sorted(fused_scores.items(), key=lambda item: item[1], reverse=True)

        # Map the sorted doc_ids back to Document objects
        final_docs = [doc_store[doc_id] for doc_id, _ in reranked_results]
        return final_docs
