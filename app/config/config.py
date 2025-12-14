# app/config/config.py
"""
Unified configuration module for CookHero.
Provides a single entry point for all application configuration.

Design:
- Settings: Top-level configuration class containing global and module configs
- All configs loaded from config.yml + .env secrets
"""

from pydantic import BaseModel

from app.config.llm_config import LLMProviderConfig
from app.config.rag_config import RAGConfig
from app.config.config_loader import load_llm_config, load_rag_config


class Settings(BaseModel):
    """
    Top-level application settings.
    
    Contains:
    1. Global configuration (API prefix, project name, etc.)
    2. Global LLM provider configuration
    3. Module-specific configurations (RAG, etc.)
    """
    # ==========================================================================
    # Global Configuration
    # ==========================================================================
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "CookHero"
    DEBUG: bool = False
    
    # ==========================================================================
    # Module Configurations
    # ==========================================================================
    # Global LLM provider configuration
    llm: LLMProviderConfig = load_llm_config()

    # RAG configuration loaded from config.yml
    rag: RAGConfig = load_rag_config(llm)
    
    class Config:
        arbitrary_types_allowed = True


# Single global settings instance
settings = Settings()

# Convenience alias for backward compatibility
DefaultRAGConfig = settings.rag
