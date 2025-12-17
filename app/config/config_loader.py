# app/config/config_loader.py
"""
Configuration loader for CookHero.
Loads from config.yml and merges with secrets from environment variables.

Environment variable loading:
- Uses load_dotenv() to load .env file into os.environ
- All sensitive params are read from os.getenv()
- Supports inheritance (e.g., RERANKER_API_KEY falls back to LLM_API_KEY)
"""

import os
from pathlib import Path
from typing import Any, Dict

import yaml
from dotenv import load_dotenv

from app.config.database_config import (
    DatabaseConfig,
    MilvusConfig,
    PostgresConfig,
    RedisConfig,
)
from app.config.llm_config import LLMProviderConfig
from app.config.rag_config import RAGConfig


# Load .env file into environment variables at module import
load_dotenv()


def _load_config_data() -> Dict[str, Any]:
    """Load raw YAML config as a dict."""
    config_path = Path("config.yml")
    if not config_path.exists():
        raise FileNotFoundError("config.yml not found in the project root.")

    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_llm_config() -> LLMProviderConfig:
    """
    Load global LLM provider configuration.
    
    Environment variables:
    - LLM_API_KEY: API key for LLM provider
    """
    config_data = _load_config_data()
    llm_data = config_data.get("llm", {}) or {}

    # Load API key from environment
    llm_api_key = os.getenv("LLM_API_KEY")
    if llm_api_key:
        llm_data["api_key"] = llm_api_key

    return LLMProviderConfig.model_validate(llm_data)


def load_database_config() -> DatabaseConfig:
    """
    Load database configuration for PostgreSQL, Redis, and Milvus.
    
    Environment variables:
    - DATABASE_PASSWORD: PostgreSQL password
    - REDIS_PASSWORD: Redis password
    - MILVUS_USER: Milvus username
    - MILVUS_PASSWORD: Milvus password
    """
    config_data = _load_config_data()
    db_root = config_data.get("database", {}) or {}

    # PostgreSQL config from database.postgres
    pg_data = dict(db_root.get("postgres", {}) or {})
    db_password = os.getenv("DATABASE_PASSWORD")
    if db_password:
        pg_data["password"] = db_password
    postgres_config = PostgresConfig.model_validate(pg_data)

    # Redis config from database.redis
    redis_data = dict(db_root.get("redis", {}) or {})
    redis_password = os.getenv("REDIS_PASSWORD")
    if redis_password:
        redis_data["password"] = redis_password
    redis_config = RedisConfig.model_validate(redis_data)

    # Milvus config from database.milvus
    milvus_data = dict(db_root.get("milvus", {}) or {})
    milvus_user = os.getenv("MILVUS_USER")
    milvus_password = os.getenv("MILVUS_PASSWORD")
    if milvus_user:
        milvus_data["user"] = milvus_user
    if milvus_password:
        milvus_data["password"] = milvus_password
    milvus_config = MilvusConfig.model_validate(milvus_data)

    return DatabaseConfig(
        postgres=postgres_config,
        redis=redis_config,
        milvus=milvus_config,
    )


def load_rag_config(llm_config: LLMProviderConfig | None = None) -> RAGConfig:
    """
    Load RAG configuration from YAML + environment variables.
    
    Environment variables:
    - RERANKER_API_KEY: Dedicated reranker API key (falls back to LLM_API_KEY)
    
    Args:
        llm_config: Global LLM config for API key fallback
    """
    config_data = _load_config_data()

    # Build RAG config data (excluding database sections)
    rag_data: Dict[str, Any] = {}

    # Copy RAG-specific sections
    for key in ["paths", "embedding", "retrieval", "data_source"]:
        if key in config_data:
            rag_data[key] = config_data[key]

    # Vector store config (without host/port, those are in DatabaseConfig)
    vs_data = config_data.get("vector_store", {}) or {}
    rag_data["vector_store"] = {
        "type": vs_data.get("type", "milvus"),
        "collection_names": vs_data.get("collection_names", {}),
    }

    # Reranker config with API key inheritance
    reranker_data = config_data.get("reranker", {}) or {}
    
    # API key priority: RERANKER_API_KEY > reranker.api_key in yaml > LLM_API_KEY
    reranker_api_key = os.getenv("RERANKER_API_KEY")
    if reranker_api_key:
        reranker_data["api_key"] = reranker_api_key
    elif not reranker_data.get("api_key") and llm_config and llm_config.api_key:
        # Fall back to global LLM API key
        reranker_data["api_key"] = llm_config.api_key
    
    rag_data["reranker"] = reranker_data

    # Cache config (without connection details, those are in DatabaseConfig)
    cache_data = config_data.get("cache", {}) or {}
    rag_data["cache"] = {
        "enabled": cache_data.get("enabled", True),
        "ttl": cache_data.get("ttl", 3600),
        "l2_enabled": cache_data.get("l2_enabled", True),
        "similarity_threshold": cache_data.get("similarity_threshold", 0.92),
        "vector_collection": cache_data.get("vector_collection", "cookhero_retrieval_cache"),
    }

    return RAGConfig.model_validate(rag_data)
