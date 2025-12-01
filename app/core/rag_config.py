# app/core/rag_config.py
from pydantic import BaseModel, Field
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
    mode: Literal['local', 'remote']
    local_model: str
    remote_model: str
    api_url: str
    batch_size: int
    api_key: Optional[str] = None  # Sensitive, will be loaded from .env

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

class HowToCookConfig(BaseModel):
    path_suffix: str
    headers_to_split_on: List[List[str]]

class TipsConfig(BaseModel):
    path_suffix: str
    headers_to_split_on: List[List[str]]

class DataSourceConfig(BaseModel):
    howtocook: HowToCookConfig
    tips: TipsConfig

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
    data_source: DataSourceConfig


