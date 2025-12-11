# app/core/rag_config.py
from pydantic import BaseModel, Field, model_validator
from typing import List, Literal, Optional, Dict

# --- Nested Configuration Models ---

class PathsConfig(BaseModel):
    base_data_path: str

class VectorStoreConfig(BaseModel):
    type: str
    host: str
    port: int
    collection_names: Dict[str, str]

class EmbeddingConfig(BaseModel):
    model_name: str

class LLMConfig(BaseModel):
    model_name: str
    base_url: Optional[str] = None
    temperature: float
    max_tokens: int
    api_key: Optional[str] = None  # Sensitive, will be loaded from .env

class RetrievalConfig(BaseModel):
    top_k: int
    rrf_k: int  # Deprecated: Milvus now handles RRF internally, kept for backward compatibility
    score_threshold: float = 0.0  # Minimum score threshold for filtering low-quality results
    ranker_type: Literal["rrf", "weighted"] = "rrf"  # Ranker type for hybrid search
    ranker_weights: List[float] = [0.5, 0.5]  # Weights for [dense, sparse] when using weighted ranker

class RerankerConfig(BaseModel):
    enabled: bool
    type: Literal['siliconflow']
    model_name: str
    score_threshold: float
    base_url: Optional[str] = None
    temperature: float
    max_tokens: int
    api_key: Optional[str] = None  # Sensitive, will be loaded from .env

class HowToCookConfig(BaseModel):
    path_suffix: str
    headers_to_split_on: List[List[str]]

class TipsConfig(BaseModel):
    path_suffix: str
    headers_to_split_on: List[List[str]]

class GenericTextConfig(BaseModel):
    path_suffix: str
    window_size: int = 3

class DataSourceConfig(BaseModel):
    howtocook: HowToCookConfig
    tips: TipsConfig
    generic_text: GenericTextConfig

class CacheConfig(BaseModel):
    enabled: bool = True
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None
    retrieval_ttl: int = 1800  # 30 minutes
    response_ttl: int = 3600   # 1 hour
    response_l2_enabled: bool = True
    similarity_threshold: float = 0.95
    vector_host: Optional[str] = None
    vector_port: Optional[int] = None
    vector_collection: str = "cookhero_response_cache"
    vector_user: Optional[str] = None
    vector_password: Optional[str] = None
    vector_secure: bool = False

    @model_validator(mode="before")
    @classmethod
    def _migrate_l2_field(cls, values):
        if isinstance(values, dict) and "response_l2_enabled" not in values and "l2_enabled" in values:
            values["response_l2_enabled"] = values["l2_enabled"]
        return values

# --- Main Configuration Model ---

class RAGConfig(BaseModel):
    """
    The main configuration model, composed of nested sub-models.
    This structure mirrors the `config.yml` file.
    """
    paths: PathsConfig
    vector_store: VectorStoreConfig
    embedding: EmbeddingConfig
    llm: LLMConfig
    retrieval: RetrievalConfig
    reranker: RerankerConfig
    cache: CacheConfig
    data_source: DataSourceConfig


