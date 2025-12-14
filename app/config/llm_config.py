from typing import Optional

from pydantic import BaseModel


class LLMProviderConfig(BaseModel):
    """
    Global LLM provider configuration shared across modules.
    """
    model_name: str = "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B"
    base_url: Optional[str] = "https://api.siliconflow.cn/v1"
    api_key: Optional[str] = None  # Loaded from .env
    temperature: float = 1.0
    max_tokens: int = 8192
