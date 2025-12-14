# app/config/config.py
"""
Unified configuration module for CookHero.
Combines system-wide settings with RAG configuration.
"""

from pydantic_settings import BaseSettings

from app.config.rag_config import RAGConfig
from app.config.config_loader import load_config


class Settings(BaseSettings):
    """
    System-wide settings.
    """
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "CookHero"
    
    # RAG configuration loaded from config.yml
    rag: RAGConfig = load_config()
    
    class Config:
        arbitrary_types_allowed = True


# Single global settings instance
settings = Settings()

# Convenience alias for backward compatibility
DefaultRAGConfig = settings.rag
