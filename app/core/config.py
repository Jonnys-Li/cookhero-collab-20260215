# app/core/config.py
import os
from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    """
    System-wide settings.
    """
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "CookHero"

    # Milvus settings
    MILVUS_HOST: str = os.environ.get("MILVUS_HOST", "localhost")
    MILVUS_PORT: int = int(os.environ.get("MILVUS_PORT", 19530))

    # Embedding model settings
    EMBEDDING_MODEL_NAME: str = "sentence-transformers/all-MiniLM-L6-v2"

    class Config:
        case_sensitive = True
        env_file = ".env"

settings = Settings()
