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
    
    # Access RAG configuration
    print(settings.rag.vector_store.host)
    # or use the alias:
    print(DefaultRAGConfig.vector_store.host)
"""

from app.config.config import settings, Settings, DefaultRAGConfig
from app.config.llm_config import LLMProviderConfig
from app.config.rag_config import (
    RAGConfig,
    LLMOverrideConfig,
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
    "LLMProviderConfig",
    "LLMOverrideConfig",
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
