# app/rag/cache/cache_manager.py
"""Hybrid cache manager for retrieval (L1) and optional response L2 caching."""
import hashlib
import logging
import pickle
from typing import List, Optional

import redis
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from app.rag.cache.base import KeywordCacheBackend, VectorCacheBackend
from app.rag.cache.backends import MilvusVectorCache, RedisKeywordCache

logger = logging.getLogger(__name__)


class CacheManager:
    """
    Manages caching for retrieval results and query responses using a hybrid strategy.
    
    L1 Cache (Redis):
    - Exact match based on rewritten query hash (used for retrieval documents and responses)
    - Fast lookup for identical queries
    
    L2 Cache (Vector index):
    - Semantic similarity matching based on query embeddings (Milvus)
    - Handles query variations with high similarity for responses only
    - Optional per-request when storing or reading responses
    """
    
    def __init__(
        self,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_db: int = 0,
        redis_password: Optional[str] = None,
        retrieval_ttl: int = 3600,  # 1 hour (longer than response_ttl)
        response_ttl: int = 1800,  # 30 minutes (shorter than retrieval_ttl)
        similarity_threshold: float = 0.95,
        embeddings: Optional[Embeddings] = None,
        response_l2_enabled: bool = True,
        vector_host: Optional[str] = None,
        vector_port: Optional[int] = None,
        vector_collection: str = "cookhero_response_cache",
        vector_user: Optional[str] = None,
        vector_password: Optional[str] = None,
        vector_secure: bool = False,
    ):
        """
        Initialize the cache manager.
        
        Args:
            redis_host: Redis host address
            redis_port: Redis port
            redis_db: Redis database number
            redis_password: Redis password (if required)
            retrieval_ttl: Time-to-live for retrieval cache (seconds).
                Should be longer than response_ttl so retrieval results can be
                reused even after responses expire.
            response_ttl: Time-to-live for response cache (seconds).
                Should be shorter than retrieval_ttl since users may want
                varied responses, but retrieval results change infrequently.
            similarity_threshold: Minimum similarity for L2 cache matching (0-1)
                embeddings: Embedding model for L2 semantic matching (optional)
            response_l2_enabled: Whether L2 semantic cache should be used for responses
            vector_host/vector_port: Connection info for the Milvus cache collection
            vector_collection: Milvus collection name used to store cached responses
            vector_user/vector_password: Optional Milvus credentials
            vector_secure: Whether to use TLS when connecting to Milvus
        """
        self.retrieval_ttl = retrieval_ttl
        self.response_ttl = response_ttl
        self.similarity_threshold = similarity_threshold
        self.response_l2_enabled = response_l2_enabled
        # Initialize Redis connection (for keyword cache)
        self.redis_client: Optional[redis.Redis] = None
        try:
            client = redis.Redis(
                host=redis_host,
                port=redis_port,
                db=redis_db,
                password=redis_password,
                decode_responses=False,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            client.ping()
            client.flushdb()
            self.redis_client = client
            logger.info(f"Redis connection established: {redis_host}:{redis_port}")
        except Exception as e:
            logger.warning(f"Failed to connect to Redis: {e}. Caching will be disabled.")
            self.redis_client = None

        # Backends
        self.keyword_cache: Optional[KeywordCacheBackend] = RedisKeywordCache(self.redis_client) if self.redis_client else None

        self.embeddings = embeddings
        self.vector_cache: Optional[VectorCacheBackend] = None
        self._embedding_dimension: Optional[int] = None
        if self.response_l2_enabled:
            self._embedding_dimension = self._infer_embedding_dimension()
            if embeddings is None or self._embedding_dimension is None:
                logger.warning("Response L2 cache enabled but embeddings are unavailable. Disabling L2 cache.")
                self.response_l2_enabled = False
            else:
                host = vector_host or redis_host
                port = vector_port or 19530
                try:
                    self.vector_cache = MilvusVectorCache(
                        host=host,
                        port=port,
                        collection_name=vector_collection,
                        dimension=self._embedding_dimension,
                        user=vector_user,
                        password=vector_password,
                        secure=vector_secure,
                    )
                    logger.info(
                        "Milvus L2 cache ready at %s:%s (collection=%s)",
                        host,
                        port,
                        vector_collection,
                    )
                except Exception as exc:  # pragma: no cover - optional dependency guard
                    logger.warning("Failed to initialize Milvus vector cache: %s. Disabling response L2 cache.", exc)
                    self.response_l2_enabled = False
        
    def _compute_hash(self, text: str) -> str:
        """Compute SHA256 hash of a text string."""
        return hashlib.sha256(text.encode('utf-8')).hexdigest()
    
    def _get_retrieval_key(
        self,
        data_source: str,
        rewritten_query: str,
        metadata_expression: Optional[str],
    ) -> str:
        """Generate cache key for retrieval results including metadata filters."""
        query_hash = self._compute_hash(rewritten_query)
        metadata_hash = self._compute_hash(metadata_expression or "__none__")
        return f"rag:retrieval:{data_source}:{query_hash}:{metadata_hash}"
    
    def _get_response_key(self, rewritten_query: str) -> str:
        """Generate cache key for query responses."""
        query_hash = self._compute_hash(rewritten_query)
        return f"rag:response:{query_hash}"
    
    def get_retrieval_cache(
        self,
        data_source: str,
        rewritten_query: str,
        metadata_expression: Optional[str],
    ) -> Optional[List[Document]]:
        """
        Get cached retrieval results (L1 cache only).
        
        Args:
            data_source: Name of the data source
            rewritten_query: The rewritten query string
            metadata_expression: The metadata filter expression (part of the cache key)
            
        Returns:
            Cached documents if found, None otherwise
        """
        if not self.keyword_cache:
            return None
        
        try:
            cache_key = self._get_retrieval_key(data_source, rewritten_query, metadata_expression)
            cached_data = self.keyword_cache.get(cache_key)
            
            if cached_data:
                # Deserialize documents
                docs = pickle.loads(cached_data)
                logger.info(f"Retrieval cache HIT for source '{data_source}': {len(docs)} documents")
                return docs
            else:
                logger.debug(f"Retrieval cache MISS for source '{data_source}'")
                return None
        except Exception as e:
            logger.warning(f"Error reading retrieval cache: {e}")
            return None
    
    def set_retrieval_cache(
        self,
        data_source: str,
        rewritten_query: str,
        metadata_expression: Optional[str],
        documents: List[Document]
    ) -> bool:
        """
        Cache retrieval results (L1 cache).
        
        Args:
            data_source: Name of the data source
            rewritten_query: The rewritten query string
            metadata_expression: The metadata filter expression (part of the cache key)
            documents: Documents to cache
            
        Returns:
            True if caching succeeded, False otherwise
        """
        if not self.keyword_cache:
            return False
        
        try:
            cache_key = self._get_retrieval_key(data_source, rewritten_query, metadata_expression)
            serialized = pickle.dumps(documents)
            stored = self.keyword_cache.set(cache_key, serialized, ttl_seconds=self.retrieval_ttl)
            if stored:
                logger.info(
                    "Cached retrieval results for source '%s': %d documents (TTL: %ss)",
                    data_source,
                    len(documents),
                    self.retrieval_ttl,
                )
            return stored
        except Exception as e:
            logger.warning(f"Error writing retrieval cache: {e}")
            return False
    
    def get_response_cache(
        self,
        rewritten_query: str,
        use_l2: Optional[bool] = None,
    ) -> Optional[str]:
        """
        Get cached response using hybrid strategy (L1 + L2).
        
        Args:
            rewritten_query: The rewritten query string
            use_l2: Optional override to enable/disable semantic cache lookup
                for this call.
            
        Returns:
            Cached response if found, None otherwise
        """
        # Try L1 cache first (exact match)
        if self.keyword_cache:
            try:
                cache_key = self._get_response_key(rewritten_query)
                cached_response = self.keyword_cache.get(cache_key)
                
                if cached_response:
                    response = cached_response.decode('utf-8')
                    logger.info("Response cache HIT (L1): exact match")
                    return response
            except Exception as e:
                logger.warning(f"Error reading L1 response cache: {e}")
        
        # Try L2 cache (semantic similarity)
        if self._should_use_l2(use_l2):
            assert self.embeddings is not None and self.vector_cache is not None
            try:
                query_embedding = self.embeddings.embed_query(rewritten_query)
                best_match = self.vector_cache.search(query_embedding, self.similarity_threshold)
                
                if best_match:
                    logger.info(f"Response cache HIT (L2): similarity={best_match[1]:.4f}")
                    return best_match[0]
            except Exception as e:
                logger.warning(f"Error reading L2 response cache: {e}")
        
        logger.debug("Response cache MISS")
        return None
    
    def set_response_cache(
        self,
        rewritten_query: str,
        response: str,
        use_l2: Optional[bool] = None,
    ) -> bool:
        """
        Cache query response using hybrid strategy (L1 + L2).
        
        Args:
            rewritten_query: The rewritten query string
            response: The response to cache
            use_l2: Optional override to enable/disable semantic cache storage
                for this call.
            
        Returns:
            True if caching succeeded, False otherwise
        """
        success = True
        # Store in L1 cache (exact match)
        if self.keyword_cache:
            try:
                cache_key = self._get_response_key(rewritten_query)
                success = self.keyword_cache.set(cache_key, response.encode('utf-8'), ttl_seconds=self.response_ttl)
                if success:
                    logger.info(f"Cached response (L1): TTL={self.response_ttl}s")
            except Exception as e:
                logger.warning(f"Error writing L1 response cache: {e}")
                success = False
        
        # Store in L2 cache (semantic similarity)
        if self._should_use_l2(use_l2):
            assert self.embeddings is not None and self.vector_cache is not None
            try:
                query_embedding = self.embeddings.embed_query(rewritten_query)
                query_hash = self._compute_hash(rewritten_query)
                stored = self.vector_cache.add(
                    query_hash,
                    query_embedding,
                    response,
                    ttl_seconds=self.response_ttl,
                ) 
                success = success and stored
                if stored:
                    logger.info("Cached response (L2): semantic index updated")
            except Exception as e:
                logger.warning(f"Error writing L2 response cache: {e}")
                success = False
        
        return success
    
    def clear_cache(self, cache_type: Optional[str] = None) -> bool:
        """
        Clear cache entries.
        
        Args:
            cache_type: Type of cache to clear ('retrieval', 'response', or None for all)
            
        Returns:
            True if clearing succeeded, False otherwise
        """
        if not self.keyword_cache:
            return False
        
        try:
            if cache_type == 'retrieval':
                pattern = "rag:retrieval:*"
            elif cache_type == 'response':
                pattern = "rag:response:*"
            else:
                pattern = "rag:*"
            
            cleared = self.keyword_cache.clear(pattern)
            if cleared:
                logger.info(f"Cleared cache entries matching '{pattern}'")
            else:
                logger.warning("Keyword cache clear failed for pattern '%s'", pattern)
            
            overall_success = bool(cleared)
            # Clear L2 cache if needed
            if cache_type is None or cache_type == 'response':
                if self.vector_cache:
                    overall_success = self.vector_cache.clear() and overall_success
                    logger.info("Cleared L2 semantic cache")
            
            return overall_success
        except Exception as e:
            logger.warning(f"Error clearing cache: {e}")
            return False
    
    def invalidate_data_source_cache(self, data_source: str) -> bool:
        """
        Invalidate all cache entries for a specific data source.
        
        Args:
            data_source: Name of the data source
            
        Returns:
            True if invalidation succeeded, False otherwise
        """
        if not self.keyword_cache:
            return False
        
        try:
            pattern = f"rag:retrieval:{data_source}:*"
            cleared = self.keyword_cache.clear(pattern)
            if cleared:
                logger.info(f"Invalidated cache entries for data source '{data_source}'")
            return cleared
        except Exception as e:
            logger.warning(f"Error invalidating data source cache: {e}")
            return False

    def _infer_embedding_dimension(self) -> Optional[int]:
        if not self.embeddings:
            return None
        try:
            probe = self.embeddings.embed_query("ping for dimension")
            return len(probe)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Failed to infer embedding dimension for cache: %s", exc)
            return None

    def _should_use_l2(self, override: Optional[bool]) -> bool:
        desired = self.response_l2_enabled if override is None else override
        return bool(desired and self.vector_cache and self.embeddings)
