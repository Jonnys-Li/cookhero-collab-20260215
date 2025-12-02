# app/rag/retrieval_optimization.py
import logging
from typing import List, Dict, Any, Tuple, Optional, Literal

from langchain_milvus import Milvus
from langchain_core.documents import Document

logger = logging.getLogger(__name__)

class RetrievalOptimizationModule:
    """
    Handles advanced retrieval strategies using Milvus built-in hybrid search.
    Combines dense vector search with sparse BM25 search using Milvus native capabilities.
    Supports dynamic ranker configuration and score-based filtering.
    """
    def __init__(
        self, 
        vectorstore: Milvus, 
        child_chunks: List[Document],
        score_threshold: float = 0.0,
        default_ranker_type: str = "rrf",
        default_ranker_weights: List[float] = [0.5, 0.5]
    ):
        """
        Initializes the retrieval optimization module.
        Args:
            vectorstore: The Milvus vectorstore with BM25 built-in function enabled.
            child_chunks: The list of all child document chunks (kept for compatibility).
            score_threshold: Minimum score threshold for filtering low-quality results.
            default_ranker_type: Default ranker type ("rrf" or "weighted").
            default_ranker_weights: Default weights for [dense, sparse] when using weighted ranker.
        """
        if not vectorstore:
            raise ValueError("Vectorstore must be provided.")
            
        self.vectorstore = vectorstore
        self.child_chunks = child_chunks  # Keep for potential future use
        self.score_threshold = score_threshold
        self.default_ranker_type = default_ranker_type
        self.default_ranker_weights = default_ranker_weights
        
        logger.info(f"Retrieval optimization module initialized with Milvus hybrid search")
        logger.info(f"Score threshold: {score_threshold}, Default ranker: {default_ranker_type}, Weights: {default_ranker_weights}")
        
    def hybrid_search(
        self, 
        query: str, 
        top_k: int,
        ranker_type: Optional[str] = None,
        ranker_weights: Optional[List[float]] = None,
        score_threshold: Optional[float] = None
    ) -> Tuple[List[Document], List[float]]:
        """
        Performs hybrid search using Milvus built-in BM25 and dense vector search.
        Supports dynamic ranker configuration and score-based filtering.
        
        Args:
            query: The user's search query.
            top_k: The number of documents to retrieve (before filtering).
            ranker_type: Ranker type ("rrf" or "weighted"). Uses default if None.
            ranker_weights: Weights for [dense, sparse] when using weighted ranker. Uses default if None.
            score_threshold: Minimum score threshold. Uses instance default if None.
            
        Returns:
            A tuple of (documents, scores) where both lists have the same length.
        """
        # Use defaults if not specified
        ranker_type = ranker_type or self.default_ranker_type
        ranker_weights = ranker_weights or self.default_ranker_weights
        score_threshold = score_threshold if score_threshold is not None else self.score_threshold
        
        logger.info(f"Performing Milvus hybrid search for query: '{query}'")
        logger.info(f"Parameters: top_k={top_k}, ranker_type={ranker_type}, weights={ranker_weights}, threshold={score_threshold}")
        
        # Prepare ranker parameters
        ranker_params = {}
        if ranker_type == "weighted":
            ranker_params = {"weights": ranker_weights}
        
        # Milvus hybrid search with configurable ranker
        results = self.vectorstore.similarity_search_with_score(
            query=query,
            k=top_k,
            fetch_k=int(top_k * 3),
            ranker_type=ranker_type,
            ranker_params=ranker_params if ranker_params else None
        )
        
        # Extract documents and scores
        docs = [doc for doc, score in results]
        scores = [score for doc, score in results]
        
        logger.info(f"Retrieved {len(docs)} documents from hybrid search (before filtering)")
        
        # Log each document with its score
        for i, (doc, score) in enumerate(zip(docs, scores)):
            logger.info("=" * 60)
            logger.info(f"Rank #{i+1} | Score: {score:.4f} | Doc ID: {doc.id}")
            logger.info(f"Metadata: {doc.metadata}")
            logger.info(f"Content preview: {doc.page_content[:100]}...")
        
        # Apply score threshold filtering
        if score_threshold > 0 and ranker_type == "weighted":
            filtered_results = [(doc, score) for doc, score in zip(docs, scores) if score >= score_threshold]
            filtered_docs = [doc for doc, score in filtered_results]
            filtered_scores = [score for doc, score in filtered_results]
            
            logger.info("=" * 60)
            logger.info(f"Score filtering: {len(docs)} → {len(filtered_docs)} documents (threshold: {score_threshold})")
            
            if len(filtered_docs) < len(docs):
                logger.warning(f"Filtered out {len(docs) - len(filtered_docs)} low-score documents")
                for doc, score in zip(docs, scores):
                    if score < score_threshold:
                        logger.warning(f"Filtered: Score {score:.4f} < {score_threshold} | Doc ID: {doc.id}")
            
            return filtered_docs, filtered_scores
        
        return docs, scores

    def metadata_filtered_search(
        self, 
        query: str, 
        filters: Dict[str, Any], 
        top_k: int,
        ranker_type: Optional[str] = None,
        ranker_weights: Optional[List[float]] = None
    ) -> Tuple[List[Document], List[float]]:
        """
        Performs a hybrid search and then applies metadata filters to the results.
        Note: This is a post-filtering approach. For large-scale systems, pre-filtering
        using Milvus native filtering is more efficient.
        
        Args:
            query: The user's search query.
            filters: A dictionary of metadata key-value pairs to filter on.
            top_k: The final number of documents to return.
            ranker_type: Ranker type ("rrf" or "weighted"). Uses default if None.
            ranker_weights: Weights for [dense, sparse] when using weighted ranker.
            
        Returns:
            A tuple of (documents, scores) matching the filters.
        """
        # Get a larger pool of candidates with hybrid search
        initial_docs, initial_scores = self.hybrid_search(
            query, 
            top_k * 5,
            ranker_type=ranker_type,
            ranker_weights=ranker_weights
        )
        
        # Apply filters
        filtered_results = []
        for doc, score in zip(initial_docs, initial_scores):
            is_match = all(
                doc.metadata.get(key) == value for key, value in filters.items()
            )
            if is_match:
                filtered_results.append((doc, score))
        
        logger.info(f"Found {len(filtered_results)} documents matching filters out of "
                    f"{len(initial_docs)} initial candidates.")
        
        # Return top_k results
        final_results = filtered_results[:top_k]
        final_docs = [doc for doc, score in final_results]
        final_scores = [score for doc, score in final_results]
        
        return final_docs, final_scores
    
    def intelligent_ranker_selection(self, query: str) -> Tuple[str, List[float]]:
        """
        Intelligently selects ranker type and weights based on query characteristics.
        This can be extended with more sophisticated logic or ML models.
        
        Args:
            query: The user's search query.
            
        Returns:
            A tuple of (ranker_type, weights).
        """
        query_lower = query.lower()
        
        # Keyword-heavy queries (with specific terms) → favor BM25
        keyword_indicators = ["怎么做", "如何", "步骤", "方法", "做法", "recipe", "how to", "步骤"]
        if any(indicator in query_lower for indicator in keyword_indicators):
            logger.info(f"Query contains keyword indicators, using weighted ranker with BM25 bias")
            return "weighted", [0.8, 0.2]  # Favor sparse/BM25
        
        # Semantic/conceptual queries → favor dense embeddings
        semantic_indicators = ["推荐", "类似", "什么菜", "适合", "建议", "recommend", "similar", "suggest"]
        if any(indicator in query_lower for indicator in semantic_indicators):
            logger.info(f"Query contains semantic indicators, using weighted ranker with dense bias")
            return "weighted", [1, 0]  # Favor dense/semantic
        
        # Balanced queries → use RRF
        logger.info(f"Balanced query, using RRF ranker")
        return "rrf", [0.8, 0.2]
