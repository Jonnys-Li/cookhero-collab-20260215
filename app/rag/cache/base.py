# app/rag/cache/base.py
"""
Cache backend abstractions.

- KeywordCacheBackend: key/value semantics (for exact match, e.g., Redis L1).
- VectorCacheBackend: vector insert/search semantics (for semantic match, e.g., in-memory or future Milvus).
"""
from abc import ABC, abstractmethod
from typing import Any, List, Optional, Tuple


class KeywordCacheBackend(ABC):
    """Abstract base class for keyword-based cache backends (exact match)."""
    
    @abstractmethod
    def get(self, key: str) -> Optional[bytes]:
        """Get a value by key."""
        pass
    
    @abstractmethod
    def set(self, key: str, value: bytes, ttl_seconds: int | None = None) -> bool:
        """Set a value with optional TTL."""
        pass
    
    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete a value by key."""
        pass
    
    @abstractmethod
    def clear(self, pattern: str | None = None) -> bool:
        """Clear cache entries matching pattern."""
        pass


class VectorCacheBackend(ABC):
    """Abstract base class for vector-based cache backends (semantic similarity)."""
    
    @abstractmethod
    def add(self, key: str, embedding: List[float], payload: Any) -> bool:
        """Add a vector with payload to the cache."""
        pass
    
    @abstractmethod
    def search(self, embedding: List[float], threshold: float) -> Optional[Tuple[Any, float]]:
        """Search for similar vectors, returning (payload, similarity_score) if found."""
        pass
    
    @abstractmethod
    def clear(self) -> bool:
        """Clear all cached vectors."""
        pass

