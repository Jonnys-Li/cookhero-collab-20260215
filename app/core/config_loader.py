# app/core/config_loader.py
import yaml
from pathlib import Path
from dotenv import dotenv_values
from app.core.rag_config import RAGConfig

def load_config() -> RAGConfig:
    """
    Loads configuration from a YAML file and merges it with secrets from a .env file.
    
    Returns:
        A validated RAGConfig object.
    """
    # Load base configuration from YAML file
    config_path = Path("config.yml")
    if not config_path.exists():
        raise FileNotFoundError("config.yml not found in the project root.")
        
    with open(config_path, 'r', encoding='utf-8') as f:
        config_data = yaml.safe_load(f)

    # Load sensitive data from .env file
    secrets = dotenv_values(".env")

    # Merge secrets into the config data
    llm_api_key = secrets.get("LLM_API_KEY")
    if "llm" in config_data and llm_api_key:
        config_data["llm"]["api_key"] = llm_api_key

    # For reranker, prioritize its own key, but fall back to the main LLM key
    reranker_api_key = secrets.get("RERANKER_API_KEY") or llm_api_key
    if "reranker" in config_data and reranker_api_key:
        config_data["reranker"]["api_key"] = reranker_api_key
    
    # Load Redis password from .env if cache config exists
    redis_password = secrets.get("REDIS_PASSWORD")
    if "cache" in config_data and redis_password:
        config_data["cache"]["redis_password"] = redis_password

    cache_vector_user = secrets.get("CACHE_VECTOR_USER")
    cache_vector_password = secrets.get("CACHE_VECTOR_PASSWORD")
    if "cache" in config_data:
        if cache_vector_user:
            config_data["cache"]["vector_user"] = cache_vector_user
        if cache_vector_password:
            config_data["cache"]["vector_password"] = cache_vector_password

    # Validate and return the configuration using Pydantic models
    return RAGConfig.parse_obj(config_data)

# Create a single, globally accessible config instance
# Any module can import this instance to get the configuration.
DefaultRAGConfig = load_config()
