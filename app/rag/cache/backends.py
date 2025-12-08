# app/rag/cache/backends.py
"""
Concrete implementations of cache backends.
"""
import logging
from typing import Any, List, Optional, Tuple, Dict

import redis

from app.rag.cache.base import KeywordCacheBackend, VectorCacheBackend

logger = logging.getLogger(__name__)


def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if len(vec1) != len(vec2):
        return 0.0
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    magnitude1 = sum(a * a for a in vec1) ** 0.5
    magnitude2 = sum(b * b for b in vec2) ** 0.5
    if magnitude1 == 0 or magnitude2 == 0:
        return 0.0
    return dot_product / (magnitude1 * magnitude2)


class RedisKeywordCache(KeywordCacheBackend):
    """Redis-based keyword cache backend for exact match (L1 cache)."""
    
    def __init__(self, client: redis.Redis):
        """
        Initialize Redis keyword cache backend.
        
        Args:
            client: Redis client instance
        """
        self.client = client

    def get(self, key: str) -> Optional[bytes]:
        """Get a value by key."""
        try:
            return self.client.get(key)
        except Exception as e:
            logger.warning(f"Error getting key '{key}' from Redis: {e}")
            return None

    def set(self, key: str, value: bytes, ttl_seconds: int | None = None) -> bool:
        """Set a value with optional TTL."""
        try:
            if ttl_seconds:
                self.client.setex(key, ttl_seconds, value)
            else:
                self.client.set(key, value)
            return True
        except Exception as e:
            logger.warning(f"Error setting key '{key}' in Redis: {e}")
            return False

    def delete(self, key: str) -> bool:
        """Delete a value by key."""
        try:
            self.client.delete(key)
            return True
        except Exception as e:
            logger.warning(f"Error deleting key '{key}' from Redis: {e}")
            return False

    def clear(self, pattern: str | None = None) -> bool:
        """Clear cache entries matching pattern."""
        try:
            pat = pattern or "*"
            keys = self.client.keys(pat)
            if keys:
                self.client.delete(*keys)
            return True
        except Exception as e:
            logger.warning(f"Error clearing Redis cache with pattern '{pat}': {e}")
            return False


class MemoryVectorCache(VectorCacheBackend):
    """
    In-memory vector cache backend for semantic similarity (L2 cache).
    
    Stores vectors as: {key: (embedding, payload)}
    Uses cosine similarity for search.
    """
    
    def __init__(self):
        """Initialize in-memory vector cache."""
        self.store: Dict[str, Tuple[List[float], Any]] = {}

    def add(self, key: str, embedding: List[float], payload: Any) -> bool:
        """Add a vector with payload to the cache."""
        self.store[key] = (embedding, payload)
        return True

    def search(self, embedding: List[float], threshold: float) -> Optional[Tuple[Any, float]]:
        """
        Search for similar vectors.
        
        Args:
            embedding: Query embedding vector
            threshold: Minimum similarity threshold
            
        Returns:
            Tuple of (payload, similarity_score) if found, None otherwise
        """
        best_match = None
        best_similarity = 0.0
        
        for _key, (emb, payload) in self.store.items():
            sim = _cosine_similarity(embedding, emb)
            if sim > best_similarity and sim >= threshold:
                best_similarity = sim
                best_match = payload
        
        if best_match is not None:
            logger.info(f"Memory L2 cache HIT: similarity={best_similarity:.4f}")
            return best_match, best_similarity
        
        return None

    def clear(self) -> bool:
        """Clear all cached vectors."""
        self.store.clear()
        return True

