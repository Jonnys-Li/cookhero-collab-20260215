# app/rag/cache/backends.py
"""
Cache backend abstractions for L2 semantic cache.

Backends:
- MemoryL2Backend: in-memory with max_items + LRU + TTL
- RedisVectorL2Backend: Redis-based shared cache (client-side scan similarity search)
"""
import logging
import time
import pickle
from typing import List, Optional, Tuple, Any, Dict

import redis

logger = logging.getLogger(__name__)


def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    if len(vec1) != len(vec2):
        return 0.0
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    magnitude1 = sum(a * a for a in vec1) ** 0.5
    magnitude2 = sum(b * b for b in vec2) ** 0.5
    if magnitude1 == 0 or magnitude2 == 0:
        return 0.0
    return dot_product / (magnitude1 * magnitude2)


class BaseL2Backend:
    def search(self, query_embedding: List[float], threshold: float) -> Optional[Tuple[str, float]]:
        raise NotImplementedError

    def set(self, query_hash: str, embedding: List[float], response: str) -> None:
        raise NotImplementedError

    def clear(self) -> None:
        raise NotImplementedError


class MemoryL2Backend(BaseL2Backend):
    """
    In-memory L2 cache with max_items + LRU + TTL.
    Stores: {query_hash: {"embedding": [...], "response": str, "last_access": ts, "created_at": ts}}
    """
    def __init__(self, max_items: int = 500, ttl_seconds: int = 3600):
        self.max_items = max_items
        self.ttl_seconds = ttl_seconds
        self._store: Dict[str, Dict[str, Any]] = {}

    def _evict_if_needed(self):
        if len(self._store) <= self.max_items:
            return
        # Evict least-recently-used
        sorted_items = sorted(self._store.items(), key=lambda kv: kv[1]["last_access"])
        to_evict = len(self._store) - self.max_items
        for i in range(to_evict):
            evict_key, _ = sorted_items[i]
            self._store.pop(evict_key, None)
        logger.info(f"Memory L2 evicted {to_evict} entries (max_items={self.max_items})")

    def _purge_expired(self):
        now = time.time()
        expired_keys = [
            key for key, val in self._store.items()
            if now - val["created_at"] > self.ttl_seconds
        ]
        for key in expired_keys:
            self._store.pop(key, None)
        if expired_keys:
            logger.debug(f"Memory L2 purged {len(expired_keys)} expired entries")

    def search(self, query_embedding: List[float], threshold: float) -> Optional[Tuple[str, float]]:
        self._purge_expired()
        best_match = None
        best_similarity = 0.0
        now = time.time()
        for key, val in self._store.items():
            sim = _cosine_similarity(query_embedding, val["embedding"])
            if sim > best_similarity and sim >= threshold:
                best_similarity = sim
                best_match = val["response"]
            # update LRU timestamp
            val["last_access"] = now
        if best_match:
            logger.info(f"Memory L2 HIT similarity={best_similarity:.4f}")
            return best_match, best_similarity
        return None

    def set(self, query_hash: str, embedding: List[float], response: str) -> None:
        now = time.time()
        self._store[query_hash] = {
            "embedding": embedding,
            "response": response,
            "created_at": now,
            "last_access": now,
        }
        self._evict_if_needed()

    def clear(self) -> None:
        self._store.clear()


class RedisVectorL2Backend(BaseL2Backend):
    """
    Redis-based L2 cache.
    Uses Redis as shared store; similarity search is client-side scan (bounded) to keep implementation lightweight.
    For production, enable Redis Stack vector index and replace scan with FT.SEARCH.
    """
    def __init__(
        self,
        redis_client: redis.Redis,
        ttl_seconds: int = 3600,
        max_scan: int = 2000,
    ):
        self.redis = redis_client
        self.ttl_seconds = ttl_seconds
        self.max_scan = max_scan

    def _key(self, query_hash: str) -> str:
        return f"rag:l2:{query_hash}"

    def search(self, query_embedding: List[float], threshold: float) -> Optional[Tuple[str, float]]:
        try:
            cursor = 0
            scanned = 0
            best_match = None
            best_similarity = 0.0
            while True:
                cursor, keys = self.redis.scan(cursor=cursor, match="rag:l2:*", count=200)
                for k in keys:
                    if scanned >= self.max_scan:
                        break
                    scanned += 1
                    data = self.redis.get(k)
                    if not data:
                        continue
                    try:
                        payload = pickle.loads(data)
                        emb = payload.get("embedding")
                        resp = payload.get("response")
                        created_at = payload.get("created_at", 0)
                        if time.time() - created_at > self.ttl_seconds:
                            continue
                        sim = _cosine_similarity(query_embedding, emb)
                        if sim > best_similarity and sim >= threshold:
                            best_similarity = sim
                            best_match = resp
                    except Exception:
                        continue
                if cursor == 0 or scanned >= self.max_scan:
                    break
            if best_match:
                logger.info(f"Redis-vector L2 HIT similarity={best_similarity:.4f} scanned={scanned}")
                return best_match, best_similarity
            return None
        except Exception as e:
            logger.warning(f"Redis-vector L2 search failed: {e}")
            return None

    def set(self, query_hash: str, embedding: List[float], response: str) -> None:
        try:
            payload = {
                "embedding": embedding,
                "response": response,
                "created_at": time.time(),
            }
            self.redis.setex(self._key(query_hash), self.ttl_seconds, pickle.dumps(payload))
        except Exception as e:
            logger.warning(f"Redis-vector L2 set failed: {e}")

    def clear(self) -> None:
        try:
            cursor = 0
            while True:
                cursor, keys = self.redis.scan(cursor=cursor, match="rag:l2:*", count=200)
                if keys:
                    self.redis.delete(*keys)
                if cursor == 0:
                    break
        except Exception as e:
            logger.warning(f"Redis-vector L2 clear failed: {e}")

