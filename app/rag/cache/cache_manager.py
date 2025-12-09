# app/rag/cache/cache_manager.py
"""
Cache Manager implementing hybrid caching strategy:
- L1 Cache: Exact match based on rewritten query hash (Redis)
- L2 Cache: Semantic similarity matching based on query embeddings (in-memory)
"""
import hashlib
import logging
import pickle
from typing import List, Optional

import redis
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from app.rag.cache.base import KeywordCacheBackend, VectorCacheBackend
from app.rag.cache.backends import RedisKeywordCache, MemoryVectorCache

logger = logging.getLogger(__name__)


class CacheManager:
    """
    Manages caching for retrieval results and query responses using a hybrid strategy.
    
    L1 Cache (Redis):
    - Exact match based on rewritten query hash
    - Fast lookup for identical queries
    
    L2 Cache (In-Memory):
    - Semantic similarity matching based on query embeddings
    - Handles query variations with high similarity
    - Uses cosine similarity to find similar cached queries
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
        l2_enabled: bool = True
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
            l2_enabled: Whether to enable L2 semantic cache
        """
        self.retrieval_ttl = retrieval_ttl
        self.response_ttl = response_ttl
        self.similarity_threshold = similarity_threshold
        self.l2_enabled = l2_enabled
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
        if l2_enabled and embeddings is None:
            logger.warning("L2 cache enabled but no embeddings provided. L2 cache will be disabled.")
            self.l2_enabled = False

        self.vector_cache: Optional[VectorCacheBackend] = MemoryVectorCache() if self.l2_enabled else None
        
    def _compute_hash(self, text: str) -> str:
        """Compute SHA256 hash of a text string."""
        return hashlib.sha256(text.encode('utf-8')).hexdigest()
    
    def _get_retrieval_key(self, data_source: str, rewritten_query: str) -> str:
        """Generate cache key for retrieval results."""
        query_hash = self._compute_hash(rewritten_query)
        return f"rag:retrieval:{data_source}:{query_hash}"
    
    def _get_response_key(self, rewritten_query: str) -> str:
        """Generate cache key for query responses."""
        query_hash = self._compute_hash(rewritten_query)
        return f"rag:response:{query_hash}"
    
    def get_retrieval_cache(
        self, 
        data_source: str, 
        rewritten_query: str
    ) -> Optional[List[Document]]:
        """
        Get cached retrieval results (L1 cache only).
        
        Args:
            data_source: Name of the data source
            rewritten_query: The rewritten query string
            
        Returns:
            Cached documents if found, None otherwise
        """
        if not self.keyword_cache:
            return None
        
        try:
            cache_key = self._get_retrieval_key(data_source, rewritten_query)
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
        documents: List[Document]
    ) -> bool:
        """
        Cache retrieval results (L1 cache).
        
        Args:
            data_source: Name of the data source
            rewritten_query: The rewritten query string
            documents: Documents to cache
            
        Returns:
            True if caching succeeded, False otherwise
        """
        if not self.keyword_cache:
            return False
        
        try:
            cache_key = self._get_retrieval_key(data_source, rewritten_query)
            # Serialize documents
            serialized = pickle.dumps(documents)
            self.keyword_cache.set(cache_key, serialized, ttl_seconds=self.retrieval_ttl)
            logger.info(f"Cached retrieval results for source '{data_source}': {len(documents)} documents (TTL: {self.retrieval_ttl}s)")
            return True
        except Exception as e:
            logger.warning(f"Error writing retrieval cache: {e}")
            return False
    
    def get_response_cache(
        self,
        rewritten_query: str
    ) -> Optional[str]:
        """
        Get cached response using hybrid strategy (L1 + L2).
        
        Args:
            rewritten_query: The rewritten query string
            
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
        if self.l2_enabled and self.embeddings and self.vector_cache:
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
    ) -> bool:
        """
        Cache query response using hybrid strategy (L1 + L2).
        
        Args:
            rewritten_query: The rewritten query string
            response: The response to cache
            use_deterministic: If True, cache with temperature=0 (deterministic)
            
        Returns:
            True if caching succeeded, False otherwise
        """
        # Store in L1 cache (exact match)
        if self.keyword_cache:
            try:
                cache_key = self._get_response_key(rewritten_query)
                self.keyword_cache.set(cache_key, response.encode('utf-8'), ttl_seconds=self.response_ttl)
                logger.info(f"Cached response (L1): TTL={self.response_ttl}s")
            except Exception as e:
                logger.warning(f"Error writing L1 response cache: {e}")
        
        # Store in L2 cache (semantic similarity)
        if self.l2_enabled and self.embeddings and self.vector_cache:
            try:
                query_embedding = self.embeddings.embed_query(rewritten_query)
                query_hash = self._compute_hash(rewritten_query)
                self.vector_cache.add(query_hash, query_embedding, response)
                logger.info("Cached response (L2): semantic index updated")
            except Exception as e:
                logger.warning(f"Error writing L2 response cache: {e}")
        
        return True
    
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
            
            self.keyword_cache.clear(pattern)
            logger.info(f"Cleared cache entries matching '{pattern}'")
            
            # Clear L2 cache if needed
            if cache_type is None or cache_type == 'response':
                if self.vector_cache:
                    self.vector_cache.clear()
                logger.info("Cleared L2 semantic cache")
            
            return True
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
            self.keyword_cache.clear(pattern)
            logger.info(f"Invalidated cache entries for data source '{data_source}'")
            return True
        except Exception as e:
            logger.warning(f"Error invalidating data source cache: {e}")
            return False

