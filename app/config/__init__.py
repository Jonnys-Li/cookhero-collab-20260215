# app/config/__init__.py
"""
Configuration module for CookHero.
Provides unified access to all configuration settings.

Usage:
    from app.config import settings, DefaultRAGConfig
    
    # Access global settings
    print(settings.PROJECT_NAME)
    
    # Access global LLM configuration
    print(settings.llm.model_name)
    
    # Access database configurations
    print(settings.database.postgres.host)
    print(settings.database.redis.host)
    print(settings.database.milvus.host)
    
    # Access RAG configuration
    print(settings.rag.vector_store.collection_names)
    # or use the alias:
    print(DefaultRAGConfig.vector_store.collection_names)
"""

from app.config.config import settings, Settings, DefaultRAGConfig
from app.config.database_config import (
    DatabaseConfig,
    PostgresConfig,
    RedisConfig,
    MilvusConfig,
)
from app.config.llm_config import LLMProviderConfig
from app.config.rag_config import (
    RAGConfig,
    PathsConfig,
    VectorStoreConfig,
    EmbeddingConfig,
    RetrievalConfig,
    RerankerConfig,
    CacheConfig,
    DataSourceConfig,
    HowToCookConfig,
    TipsConfig,
)

__all__ = [
    # Main settings
    "settings",
    "Settings",
    "DefaultRAGConfig",
    # Database configuration classes
    "DatabaseConfig",
    "PostgresConfig",
    "RedisConfig",
    "MilvusConfig",
    # LLM configuration
    "LLMProviderConfig",
    # RAG configuration classes
    "RAGConfig",
    "PathsConfig",
    "VectorStoreConfig",
    "EmbeddingConfig",
    "RetrievalConfig",
    "RerankerConfig",
    "CacheConfig",
    "DataSourceConfig",
    "HowToCookConfig",
    "TipsConfig",
]
