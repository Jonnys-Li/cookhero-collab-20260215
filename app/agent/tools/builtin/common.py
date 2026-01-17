"""
内置 Tool 集合

提供一些常用的内置 Tool 示例。
"""

import asyncio
import logging
from typing import Optional

from app.agent.tools.base import BaseTool
from app.agent.types import ToolResult
from app.agent.registry import AgentHub

logger = logging.getLogger(__name__)


class CalculatorTool(BaseTool):
    """
    计算器 Tool。

    支持基本的数学运算。
    """

    name = "calculator"
    description = "执行数学计算。支持加减乘除、幂运算、三角函数等。"
    parameters = {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "要计算的数学表达式，如 '2 + 3 * 4' 或 'math.sqrt(16)'",
            }
        },
        "required": ["expression"],
    }

    async def execute(self, expression: str = "", **kwargs) -> ToolResult:
        """执行数学计算。"""
        if not expression:
            return ToolResult(success=False, error="Expression is required")

        try:
            # 安全的数学运算环境
            import math

            safe_dict = {
                "abs": abs,
                "round": round,
                "min": min,
                "max": max,
                "sum": sum,
                "pow": pow,
                "math": math,
            }

            result = eval(expression, {"__builtins__": {}}, safe_dict)

            return ToolResult(
                success=True, data={"expression": expression, "result": result}
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Calculation failed: {str(e)}")


class DateTimeTool(BaseTool):
    """
    日期时间 Tool。

    获取当前日期时间或进行日期计算。
    """

    name = "datetime"
    description = "获取当前日期时间信息。"
    parameters = {
        "type": "object",
        "properties": {
            "format": {
                "type": "string",
                "description": "日期时间格式，如 '%Y-%m-%d %H:%M:%S'",
                "default": "%Y-%m-%d %H:%M:%S",
            },
            "timezone": {
                "type": "string",
                "description": "时区，如 'Asia/Shanghai'",
                "default": "UTC",
            },
        },
        "required": [],
    }

    async def execute(
        self, format: str = "%Y-%m-%d %H:%M:%S", timezone: str = "UTC", **kwargs
    ) -> ToolResult:
        try:
            from datetime import datetime
            from zoneinfo import ZoneInfo

            # 1. 解析时区
            try:
                tz = ZoneInfo(timezone)
            except Exception:
                return ToolResult(success=False, error=f"Invalid timezone: {timezone}")

            # 2. 获取带时区的当前时间
            now = datetime.now(tz=tz)

            # 3. 格式化
            formatted = now.strftime(format)

            return ToolResult(
                success=True,
                data={
                    "datetime": formatted,
                    "timestamp": now.timestamp(),
                    "year": now.year,
                    "month": now.month,
                    "day": now.day,
                    "weekday": now.strftime("%A"),
                    "timezone": timezone,
                },
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to get datetime: {str(e)}")


class WebSearchTool(BaseTool):
    """
    网络搜索 Tool。

    使用 Tavily API 搜索互联网获取最新信息。
    """

    name = "web_search"
    description = "搜索互联网获取最新信息。适用于需要实时数据、新闻、事件等场景。"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词"},
            "max_results": {
                "type": "integer",
                "description": "最大结果数量 (1-10)",
                "default": 5,
            },
            "search_depth": {
                "type": "string",
                "enum": ["basic", "advanced"],
                "default": "basic",
                "description": "搜索深度：basic 快速搜索，advanced 深度搜索",
            },
            "include_domains": {
                "type": "array",
                "items": {"type": "string"},
                "description": "限定搜索域名列表",
            },
            "exclude_domains": {
                "type": "array",
                "items": {"type": "string"},
                "description": "排除搜索域名列表",
            },
        },
        "required": ["query"],
    }

    async def execute(
        self,
        query: str = "",
        max_results: int = 5,
        search_depth: str = "basic",
        include_domains: Optional[list[str]] = None,
        exclude_domains: Optional[list[str]] = None,
        **kwargs,
    ) -> ToolResult:
        """执行网络搜索。"""
        if not query:
            return ToolResult(success=False, error="Query is required")

        try:
            from tavily import TavilyClient
            from app.config import settings

            api_key = settings.web_search.api_key
            if not api_key:
                return ToolResult(
                    success=False,
                    error="Web search API key is not configured",
                )

            client = TavilyClient(api_key=api_key)

            # Build search parameters
            search_params = {
                "query": query,
                "max_results": min(max(1, max_results), 10),
                "search_depth": search_depth,
                "include_answer": True,
            }

            if include_domains:
                search_params["include_domains"] = include_domains
            if exclude_domains:
                search_params["exclude_domains"] = exclude_domains

            # Execute search
            response = await asyncio.to_thread(client.search, **search_params)

            # Format results
            results = []
            for result in response.get("results", []):
                results.append(
                    {
                        "title": result.get("title", ""),
                        "url": result.get("url", ""),
                        "content": result.get("content", ""),
                        "score": result.get("score", 0),
                    }
                )

            return ToolResult(
                success=True,
                data={
                    "query": query,
                    "results": results,
                    "answer": response.get("answer"),
                },
            )

        except ImportError:
            return ToolResult(
                success=False,
                error="tavily package is not installed. Run: pip install tavily-python",
            )
        except Exception as e:
            logger.exception(f"Web search failed: {e}")
            return ToolResult(success=False, error=f"Web search failed: {str(e)}")


class ImageGeneratorTool(BaseTool):
    """
    图片生成 Tool。

    使用 OpenAI 兼容的 API 根据文本描述生成图片。
    支持 DALL-E 3 以及其他 OpenAI 兼容的图片生成服务。
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
                "enum": ["1024x1024", "1792x1024", "1024x1792"],
                "default": "1024x1024",
                "description": "图片尺寸",
            },
            "quality": {
                "type": "string",
                "enum": ["standard", "hd"],
                "default": "standard",
                "description": "图片质量：standard 标准，hd 高清",
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

    async def execute(
        self,
        prompt: str = "",
        size: str = "1024x1024",
        quality: str = "standard",
        style: str = "vivid",
        **kwargs,
    ) -> ToolResult:
        """生成图片。"""
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

            client = AsyncOpenAI(**client_kwargs)

            # Generate image
            response = await client.images.generate(
                model=config.model,
                prompt=prompt,
                size=size,
                quality=quality,
                style=style,
                n=1,
            )

            # Get the generated image URL
            image_data = response.data[0]

            return ToolResult(
                success=True,
                data={
                    "prompt": prompt,
                    "url": image_data.url,
                    "revised_prompt": image_data.revised_prompt,
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


def register_builtin_tools():
    AgentHub.register_tool(CalculatorTool(), provider="builtin")
    AgentHub.register_tool(DateTimeTool(), provider="builtin")
    AgentHub.register_tool(WebSearchTool(), provider="builtin")
    AgentHub.register_tool(ImageGeneratorTool(), provider="builtin")
