"""
Vision Model Configuration
Configures visual understanding capabilities for multimodal conversations.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class VisionModelConfig(BaseModel):
    """Configuration for vision/multimodal model."""

    # Enable/disable vision features
    enabled: bool = True

    # Model configuration (OpenAI-compatible API)
    model_name: str = "Qwen/QVQ-72B-Preview"
    base_url: str = "https://api-inference.modelscope.cn/v1"
    api_key: Optional[str] = None  # Loaded from .env (VISION_API_KEY or LLM_API_KEY)

    # Model parameters
    temperature: float = 0.7
    max_tokens: int = 4096

    # Image processing settings
    max_image_size_mb: float = 10.0  # Maximum image size in MB
    supported_formats: list[str] = Field(
        default_factory=lambda: ["image/jpeg", "image/png", "image/gif", "image/webp"]
    )

    # Timeouts
    request_timeout: int = 120  # seconds


class ImageGenerationConfig(BaseModel):
    """
    Configuration for image generation using OpenAI-compatible API (DALL-E 3, etc.).
    """

    enabled: bool = True
    api_key: Optional[str] = None  # Loaded from .env (OPENAI_IMAGE_API_KEY)
    base_url: Optional[str] = None  # Optional custom base URL for OpenAI-compatible APIs
    model: str = "dall-e-3"
    temperature: float = 1.0  # Only used for some compatible APIs


class VisionConfig(BaseModel):
    """Top-level vision configuration."""

    model: VisionModelConfig = Field(default_factory=VisionModelConfig)

    # Domain detection settings
    food_related_keywords: list[str] = Field(
        default_factory=lambda: [
            "菜品", "食材", "烹饪", "做菜", "食物", "美食", "饭菜",
            "炒", "煮", "蒸", "烤", "煎", "炸", "焖", "炖",
            "蔬菜", "水果", "肉类", "海鲜", "调料", "配料",
            "早餐", "午餐", "晚餐", "甜点", "饮品",
            "厨房", "刀工", "火候", "调味"
        ]
    )
