# app/config/rag_config.py
"""
RAG (Retrieval-Augmented Generation) configuration models.
These models define the structure for the config.yml file.

Design principles:
1. Common/shared configurations are extracted to avoid duplication
2. Module-specific configs only define their unique fields
3. Configs inherit common fields when not explicitly set
"""

from pydantic import BaseModel
from typing import List, Literal, Optional, Dict



# =============================================================================
# Common/Shared Configurations
# =============================================================================

class LLMOverrideConfig(BaseModel):
    """
    Optional per-module LLM overrides.
    Only set fields that differ from the global LLM provider config.
    """
    model_name: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


# =============================================================================
# RAG-Specific Configurations
# =============================================================================

class PathsConfig(BaseModel):
    """Data paths configuration."""
    base_data_path: str = "data/HowToCook"


class VectorStoreConfig(BaseModel):
    """Vector database configuration."""
    type: Literal["milvus"] = "milvus"
    host: str = "localhost"
    port: int = 19530
    collection_names: Dict[str, str] = {
        "recipes": "cook_hero_recipes",
        "tips": "cook_hero_tips",
    }


class EmbeddingConfig(BaseModel):
    """Embedding model configuration."""
    model_name: str = "BAAI/bge-small-zh-v1.5"


class RetrievalConfig(BaseModel):
    """Retrieval pipeline configuration."""
    top_k: int = 9
    score_threshold: float = 0.2
    ranker_type: Literal["rrf", "weighted"] = "weighted"
    ranker_weights: List[float] = [0.8, 0.2]  # [dense, sparse]


class RerankerConfig(BaseModel):
    """
    Reranker configuration.
    Inherits common LLM provider fields but can override them.
    """
    enabled: bool = True
    type: Literal["siliconflow"] = "siliconflow"
    model_name: str = "Qwen/Qwen3-Reranker-8B"
    base_url: Optional[str] = "https://api.siliconflow.cn/v1/rerank"
    api_key: Optional[str] = None  # Falls back to common LLM API key
    temperature: float = 0.0
    max_tokens: int = 8192
    score_threshold: float = 0.1


class CacheConfig(BaseModel):
    """
    Cache configuration for RAG retrieval results.
    
    Cache strategy:
    - L1: Exact match (Redis) - fast lookup for identical queries
    - L2: Semantic match (Milvus) - handles similar queries
    
    Note: Only caches Query -> Retrieved Documents, NOT LLM responses.
    """
    enabled: bool = True
    # Redis (L1 cache)
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None  # Set in .env
    # TTL for both L1 and L2
    ttl: int = 3600  # 1 hour
    # L2 semantic cache
    l2_enabled: bool = True
    similarity_threshold: float = 0.92
    vector_host: Optional[str] = None  # Falls back to vector_store.host
    vector_port: Optional[int] = None  # Falls back to vector_store.port
    vector_collection: str = "cookhero_retrieval_cache"
    vector_user: Optional[str] = None  # Set in .env
    vector_password: Optional[str] = None  # Set in .env
    vector_secure: bool = False


class HowToCookConfig(BaseModel):
    """HowToCook recipe data source configuration."""
    path_suffix: str = "dishes"
    headers_to_split_on: List[List[str]] = [["#", "header_1"], ["##", "header_2"]]


class TipsConfig(BaseModel):
    """Tips data source configuration."""
    path_suffix: str = "tips"
    headers_to_split_on: List[List[str]] = [["#", "header_1"], ["##", "header_2"]]


class DataSourceConfig(BaseModel):
    """Data sources configuration."""
    howtocook: HowToCookConfig = HowToCookConfig()
    tips: TipsConfig = TipsConfig()


# =============================================================================
# Main RAG Configuration
# =============================================================================

class RAGConfig(BaseModel):
    """
    Main RAG configuration model (does not own LLM provider defaults).
    
    Uses global LLMProviderConfig from settings; modules may provide
    optional overrides where needed.
    """
    # Optional per-module LLM override
    llm_override: Optional[LLMOverrideConfig] = None

    # Module configurations
    paths: PathsConfig = PathsConfig()
    embedding: EmbeddingConfig = EmbeddingConfig()
    vector_store: VectorStoreConfig = VectorStoreConfig()
    retrieval: RetrievalConfig = RetrievalConfig()
    reranker: RerankerConfig = RerankerConfig()
    cache: CacheConfig = CacheConfig()
    data_source: DataSourceConfig = DataSourceConfig()


