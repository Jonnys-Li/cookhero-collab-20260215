# app/agent/tools/common/image_generator.py
"""
图片生成 Tool

使用 OpenAI 兼容的 API 根据文本描述生成图片。
支持 DALL-E 3 以及其他 OpenAI 兼容的图片生成服务。
生成后自动上传到 imgbb 图床进行持久化存储。
"""

import logging
from typing import Optional

import httpx

from app.agent.tools.base import BaseTool
from app.agent.types import ToolResult

logger = logging.getLogger(__name__)


class ImageGeneratorTool(BaseTool):
    """
    图片生成 Tool。

    使用 OpenAI 兼容的 API 根据文本描述生成图片。
    支持 DALL-E 3 以及其他 OpenAI 兼容的图片生成服务。
    生成后自动上传到 imgbb 图床进行持久化存储。
    """

    name = "image_generator"
    description = "根据文本描述生成图片。使用 AI 绘图能力创建图像。"
    parameters = {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "图片描述，详细描述想要生成的图像内容",
            },
            "size": {
                "type": "string",
                "enum": ["auto", "1024x1024", "1536x1024", "1024x1536", "256x256", "512x512", "1792x1024", "1024x1792"],
                "default": "1536x1024",
                "description": "图片尺寸",
            },
            "quality": {
                "type": "string",
                "enum": ["standard", "hd", "auto"],
                "default": "standard",
                "description": "图片质量：standard 标准，hd 高清，auto 根据需求自动选择",
            },
            "style": {
                "type": "string",
                "enum": ["vivid", "natural"],
                "default": "vivid",
                "description": "图片风格：vivid 生动，natural 自然",
            },
        },
        "required": ["prompt"],
    }

    async def _upload_to_imgbb(self, image_url: str) -> Optional[dict]:
        """
        将图片 URL 上传到 imgbb 进行持久化存储。

        Args:
            image_url: 原始图片 URL

        Returns:
            包含 imgbb 上传结果的字典，失败时返回 None
        """
        from app.config import settings

        storage_config = settings.image_storage
        if not storage_config.enabled:
            logger.info("Image storage is disabled, skipping upload")
            return None

        if not storage_config.api_key:
            logger.warning("imgbb API key is not configured, skipping upload")
            return None

        try:
            params = {
                "key": storage_config.api_key,
                "image": image_url,
            }
            if storage_config.expiration:
                params["expiration"] = str(storage_config.expiration)

            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    storage_config.upload_url,
                    data=params,
                )
                response.raise_for_status()
                result = response.json()

                if result.get("success"):
                    return {
                        "url": result["data"]["url"],
                        "display_url": result["data"]["display_url"],
                        "delete_url": result["data"]["delete_url"],
                        "thumb_url": result["data"].get("thumb", {}).get("url"),
                    }
                else:
                    logger.error(f"imgbb upload failed: {result}")
                    return None

        except Exception as e:
            logger.exception(f"Failed to upload image to imgbb: {e}")
            return None

    async def execute(
        self,
        prompt: str = "",
        size: str = "1024x1024",
        quality: str = "standard",
        style: str = "vivid",
        **kwargs,
    ) -> ToolResult:
        """生成图片并上传到 imgbb 持久化存储。"""
        if not prompt:
            return ToolResult(success=False, error="Prompt is required")

        try:
            from openai import AsyncOpenAI
            from app.config import settings

            config = settings.image_generation
            api_key = config.api_key
            if not api_key:
                return ToolResult(
                    success=False,
                    error="Image generation API key is not configured",
                )

            if not config.enabled:
                return ToolResult(
                    success=False,
                    error="Image generation is disabled",
                )

            # Create client with optional base_url for OpenAI-compatible APIs
            client_kwargs = {"api_key": api_key}
            if config.base_url:
                client_kwargs["base_url"] = config.base_url

            client = AsyncOpenAI(
                **client_kwargs, # type: ignore
            )

            # Generate image
            response = await client.images.generate(
                model=config.model,
                prompt=prompt,
                size=size, # type: ignore
                quality=quality, # type: ignore
                style=style, # type: ignore
                n=1,
            )

            # Get the generated image URL
            image_data = response.data[0] # type: ignore
            original_url = image_data.url
            revised_prompt = image_data.revised_prompt

            if not original_url:
                return ToolResult(
                    success=False,
                    error="Image generation returned no URL",
                )

            # Upload to imgbb for persistent storage
            storage_result = await self._upload_to_imgbb(original_url)

            if storage_result:
                # Use imgbb URL as the final URL
                return ToolResult(
                    success=True,
                    data={
                        "prompt": prompt,
                        "url": storage_result["url"],
                        "display_url": storage_result["display_url"],
                        "thumb_url": storage_result.get("thumb_url"),
                        "revised_prompt": revised_prompt,
                        "storage": "imgbb",
                    },
                )
            else:
                # Fallback to original URL if upload fails
                logger.warning("imgbb upload failed, using original URL")
                return ToolResult(
                    success=True,
                    data={
                        "prompt": prompt,
                        "url": original_url,
                        "revised_prompt": revised_prompt,
                        "storage": "original",
                    },
                )

        except ImportError:
            return ToolResult(
                success=False,
                error="openai package is not installed. Run: pip install openai",
            )
        except Exception as e:
            logger.exception(f"Image generation failed: {e}")
            return ToolResult(success=False, error=f"Image generation failed: {str(e)}")


__all__ = ["ImageGeneratorTool"]
