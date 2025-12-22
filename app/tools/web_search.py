# app/tools/web_search.py
"""
Web Search Tool for CookHero.

Provides two core methods:
1. decide_search() - Determines if web search is needed and generates search parameters
2. execute_search() - Executes the actual web search using Tavily API

Uses Tavily official Python client for reliable web search.
"""

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from tavily import TavilyClient

from app.config import LLMProviderConfig, settings

logger = logging.getLogger(__name__)

THRESHOLD_CONFIDENCE = 6  # Confidence threshold to decide if search is needed


@dataclass
class WebSearchParams:
    """Parameters for executing a web search."""

    query: str
    max_results: int = 5

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "max_results": self.max_results,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WebSearchParams":
        return cls(
            query=data.get("query", ""),
            max_results=data.get("max_results", 5),
        )


@dataclass
class WebSearchDecision:
    """Result of web search decision."""

    confidence: int  # 0-10, higher means more likely to need web search
    search_params: Optional[WebSearchParams] = None
    reason: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def should_search(self) -> bool:
        """Check if confidence meets threshold for searching."""
        return self.confidence >= THRESHOLD_CONFIDENCE


@dataclass
class WebSearchResult:
    """A single web search result."""

    title: str
    snippet: str  # Summary or key information
    source: str  # Site name or identifier
    url: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "snippet": self.snippet,
            "source": self.source,
            "url": self.url,
        }


# Prompt template for web search decision
WEB_SEARCH_DECISION_PROMPT_TEMPLATE = """
<|system|>
你是 CookHero 的「Web 搜索决策模块」，专门判断当前用户问题是否需要进行互联网搜索来补充回答。

【决策原则】

需要 Web 搜索（confidence 应该较高，6-10）的情况：
1. **时效性信息**
   - 询问最近的美食新闻、餐厅推荐、食材价格趋势
   - 涉及季节性食材的当前市场情况
2. **本地知识库可能不足的内容**
   - 非常规或小众菜系的详细做法
   - 特定品牌产品的使用方法
   - 需要最新研究支持的营养健康信息
3. **用户明确要求搜索网络**
   - 用户提到"搜索一下"、"网上查查"等
4. **需要对比多来源信息**
   - 用户要求比较不同做法或观点

不需要 Web 搜索（confidence 应该较低，0-5）的情况：
1. **常规烹饪问题**
   - 经典菜谱、基础烹饪技巧
   - 常见食材处理方法
2. **对话延续**
   - 闲聊、确认、追问细节
   - 基于上下文的后续问题
3. **本地知识库足以回答**
   - 标准家常菜做法
   - 基础烹饪原理

【本地知识库已有的信息】
{document_summary}

<|user|>
【对话历史】
{history}

【当前问题】
{query}

【输出要求】

你 **必须且只能** 输出以下 JSON，对象结构固定，不得添加或省略字段，不得输出任何多余文本：

{{
    "confidence": <0-10的整数，越高越需要Web搜索>,
    "search_params": {{
        "query": "<优化后的搜索关键词，应简洁精准>"
    }},
    "reason": "<简短说明为什么需要或不需要Web搜索>"
}}

<|assistant|>
"""

WEB_SEARCH_DECISION_PROMPT = ChatPromptTemplate.from_template(
    WEB_SEARCH_DECISION_PROMPT_TEMPLATE
)


class WebSearchTool:
    """
    Web Search Tool providing decision and execution methods.

    Uses Tavily official Python client for web search.
    """

    def __init__(
        self,
        llm_config: Optional[LLMProviderConfig] = None,
        api_key: Optional[str] = None,
        max_results: Optional[int] = None,
    ):
        """
        Initialize the Web Search Tool.

        Args:
            llm_config: LLM configuration for decision making
            api_key: Tavily API key
            max_results: Maximum search results to return
        """
        # Load from settings with overrides
        web_search_config = settings.web_search

        self.llm_config = llm_config or settings.llm
        self.api_key = (
            api_key
            or web_search_config.api_key
            or os.getenv("WEB_SEARCH_API_KEY", "")
        )
        self.max_results = max_results or web_search_config.max_results
        self.enabled = web_search_config.enabled

        # Initialize Tavily client (lazy initialization)
        self._tavily_client: Optional[TavilyClient] = None

        # Initialize LLM for decision making
        self.llm = ChatOpenAI(
            model=self.llm_config.model_name,
            temperature=0.3,
            max_completion_tokens=131072,
            api_key=self.llm_config.api_key,  # type: ignore
            base_url=self.llm_config.base_url,
        )
        self.decision_chain = WEB_SEARCH_DECISION_PROMPT | self.llm | StrOutputParser()

        # JSON extraction regex
        self.JSON_BLOCK_RE = re.compile(
            r"```json\s*([\s\S]*?)\s*```", re.IGNORECASE
        )

    @property
    def tavily_client(self) -> Optional[TavilyClient]:
        """Lazy initialization of Tavily client."""
        if self._tavily_client is None and self.api_key:
            try:
                self._tavily_client = TavilyClient(api_key=self.api_key)
            except Exception as e:
                logger.error(f"Failed to initialize Tavily client: {e}")
        return self._tavily_client

    def _extract_first_valid_json(self, content: str) -> Dict[str, Any]:
        """Extract the first valid JSON object from LLM output."""
        # Try to extract from code block first
        for match in self.JSON_BLOCK_RE.findall(content):
            try:
                return json.loads(match)
            except json.JSONDecodeError:
                continue

        # Try to parse the entire content as JSON
        try:
            return json.loads(content.strip())
        except json.JSONDecodeError:
            pass

        # Try to find JSON object pattern
        json_pattern = re.search(r"\{[\s\S]*\}", content)
        if json_pattern:
            try:
                return json.loads(json_pattern.group())
            except json.JSONDecodeError:
                pass

        raise ValueError("No valid JSON found in response")

    async def decide_search(
        self,
        query: str,
        document_summary: Dict[str, List[str]],
        history_text: str = "",
    ) -> WebSearchDecision:
        """
        Decide whether web search is needed and generate search parameters.

        Args:
            query: Current user query
            history_text: Formatted conversation history

        Returns:
            WebSearchDecision with confidence score and search parameters
        """
        try:
            document_summary_str = ""
            if document_summary:
                dishes = document_summary.get("dish_name", [])
                document_summary_str = "已知菜品名称: " + ", ".join(dishes) + "\n"
            raw_output = await self.decision_chain.ainvoke(
                {
                    "query": query,
                    "history": history_text,
                    "document_summary": document_summary_str,
                }
            )

            parsed = self._extract_first_valid_json(raw_output)

            confidence = int(parsed.get("confidence", 0))
            confidence = max(0, min(10, confidence))  # Clamp to 0-10

            search_params = None
            if "search_params" in parsed and parsed["search_params"]:
                params_dict = parsed["search_params"]
                search_params = WebSearchParams(
                    query=params_dict.get("query", query),
                    max_results=params_dict.get("max_results", self.max_results),
                )

            return WebSearchDecision(
                confidence=confidence,
                search_params=search_params,
                reason=parsed.get("reason", ""),
                raw=parsed,
            )

        except Exception as e:
            logger.error(f"Web search decision failed: {e}", exc_info=True)
            # Return low confidence on error
            return WebSearchDecision(
                confidence=0,
                search_params=None,
                reason=f"Decision failed: {str(e)[:50]}",
                raw={},
            )

    async def execute_search(
        self,
        search_params: WebSearchParams,
    ) -> List[WebSearchResult]:
        """
        Execute web search using Tavily API.

        Args:
            search_params: Parameters for the search

        Returns:
            List of WebSearchResult objects
        """
        if not self.tavily_client:
            logger.warning("Tavily client not initialized, returning empty results")
            return []

        try:
            # Use Tavily's search method
            response = self.tavily_client.search(
                query=search_params.query,
                search_depth="basic",
                max_results=search_params.max_results,
                include_answer=False,
                include_images=False,
            )

            results = []
            for item in response.get("results", [])[: search_params.max_results]:
                results.append(
                    WebSearchResult(
                        title=item.get("title", ""),
                        snippet=item.get("content", "")[:500],  # Limit snippet length
                        source=self._extract_domain(item.get("url", "")),
                        url=item.get("url"),
                    )
                )

            logger.info(
                f"Tavily search completed: query='{search_params.query}', results={len(results)}"
            )
            return results

        except Exception as e:
            logger.error(f"Tavily search failed: {e}", exc_info=True)
            return []

    def _extract_domain(self, url: str) -> str:
        """Extract domain name from URL for source identification."""
        try:
            from urllib.parse import urlparse

            parsed = urlparse(url)
            domain = parsed.netloc
            # Remove www. prefix
            if domain.startswith("www."):
                domain = domain[4:]
            return domain
        except Exception:
            return "web"

    def format_results_for_context(
        self,
        results: List[WebSearchResult],
        max_length: int = 2000,
    ) -> str:
        """
        Format search results for inclusion in LLM context.

        Args:
            results: List of search results
            max_length: Maximum total character length

        Returns:
            Formatted string for context injection
        """
        if not results:
            return ""

        lines = []
        current_length = 0

        for i, result in enumerate(results, 1):
            entry = f"[{i}] {result.title}\n来源: {result.source}\n{result.snippet}"
            if result.url:
                entry += f"\n链接: {result.url}"
            entry += "\n"

            if current_length + len(entry) > max_length:
                break

            lines.append(entry)
            current_length += len(entry)

        return "\n".join(lines)


# Singleton instance
web_search_tool = WebSearchTool()
