# app/config/config_loader.py
"""
Configuration loader for CookHero.
Loads from config.yml and merges with secrets from .env file.
"""

from pathlib import Path
from typing import Any, Dict

import yaml
from dotenv import dotenv_values

from app.config.llm_config import LLMProviderConfig
from app.config.rag_config import RAGConfig


def _load_config_data() -> Dict[str, Any]:
    """Load raw YAML config as a dict."""
    config_path = Path("config.yml")
    if not config_path.exists():
        raise FileNotFoundError("config.yml not found in the project root.")

    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _load_secrets() -> Dict[str, Any]:
    """Load secrets from .env."""
    return dotenv_values(".env")


def load_llm_config() -> LLMProviderConfig:
    """Load global LLM provider configuration with .env overrides."""
    config_data = _load_config_data()
    secrets = _load_secrets()

    llm_data = config_data.get("llm", {}) or {}

    llm_api_key = secrets.get("LLM_API_KEY")
    if llm_api_key:
        llm_data["api_key"] = llm_api_key

    return LLMProviderConfig.model_validate(llm_data)


def load_rag_config(llm_config: LLMProviderConfig | None = None) -> RAGConfig:
    """
    Load RAG configuration from YAML + .env, excluding global LLM defaults.
    Optionally uses global LLM config to fill module fallbacks.
    """
    config_data = _load_config_data()
    secrets = _load_secrets()

    # Remove global LLM section to avoid duplication inside RAG config
    rag_data: Dict[str, Any] = {k: v for k, v in config_data.items() if k != "llm"}

    # Reranker API key fallback to global LLM key if not explicitly set
    if llm_config and llm_config.api_key:
        rag_data.setdefault("reranker", {})
        rag_data["reranker"].setdefault("api_key", llm_config.api_key)

    # Reranker dedicated secret takes precedence
    reranker_api_key = secrets.get("RERANKER_API_KEY")
    if reranker_api_key:
        rag_data.setdefault("reranker", {})
        rag_data["reranker"]["api_key"] = reranker_api_key

    # Load Redis password from .env if cache config exists
    redis_password = secrets.get("REDIS_PASSWORD")
    if redis_password:
        rag_data.setdefault("cache", {})
        rag_data["cache"]["redis_password"] = redis_password

    # Load cache vector credentials
    cache_vector_user = secrets.get("CACHE_VECTOR_USER")
    cache_vector_password = secrets.get("CACHE_VECTOR_PASSWORD")
    rag_data.setdefault("cache", {})
    if cache_vector_user:
        rag_data["cache"]["vector_user"] = cache_vector_user
    if cache_vector_password:
        rag_data["cache"]["vector_password"] = cache_vector_password

    return RAGConfig.model_validate(rag_data)
