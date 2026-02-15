# app/rag/embeddings/embedding_factory.py
import hashlib
import logging
import math
from typing import List

from langchain_core.embeddings import Embeddings

from app.config import RAGConfig

logger = logging.getLogger(__name__)


class FallbackHashEmbeddings(Embeddings):
    """
    Lightweight deterministic fallback embeddings.

    Used when local HuggingFace model loading fails, so backend can still start
    in dev/debug environments without blocking on external model downloads.
    """

    def __init__(self, dimension: int = 384):
        self.dimension = dimension

    def _embed_text(self, text: str) -> List[float]:
        seed = (text or "").encode("utf-8")
        digest = hashlib.sha256(seed).digest()
        raw = (digest * ((self.dimension // len(digest)) + 1))[: self.dimension]
        vector = [((b / 255.0) * 2.0) - 1.0 for b in raw]
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._embed_text(text) for text in texts]

    def embed_query(self, text: str) -> List[float]:
        return self._embed_text(text)


def get_embedding_model(config: RAGConfig) -> Embeddings:
    """
    Create and return embedding model.

    Strategy:
    - Prefer local HuggingFace model files (no online download at startup).
    - Fall back to deterministic hash embeddings if unavailable.
    """
    from langchain_huggingface import HuggingFaceEmbeddings

    model_name = config.embedding.model_name
    logger.info("Initializing local embedding model: %s", model_name)
    try:
        return HuggingFaceEmbeddings(
            model_name=model_name,
            model_kwargs={"device": "cpu", "local_files_only": True},
            encode_kwargs={"normalize_embeddings": True},
        )
    except Exception as exc:
        logger.warning(
            "Failed to load local embedding model '%s'. "
            "Falling back to hash embeddings. Error: %s",
            model_name,
            exc,
        )
        return FallbackHashEmbeddings()
