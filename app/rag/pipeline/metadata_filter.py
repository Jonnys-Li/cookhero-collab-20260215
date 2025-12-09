# app/rag/pipeline/metadata_filter.py
"""
LLM-driven metadata filter extraction.
Given a user query and the available metadata schema (keys + candidate values),
returns a small set of explicit filters that should be applied before retrieval.

Output format (JSON):
{
  "filters": [
    {"key": "category", "values": ["素菜", "荤菜"]},
    {"key": "difficulty", "values": ["简单"]}
  ]
}

Design principles:
- Only emit filters when用户明确提及或强烈暗示（如“素菜”、“川菜”、“甜品”、“简单”）。
- 不要因为出现模糊词就添加过滤；不确定时返回空数组。
- 只使用提供的 metadata keys 和候选值；不要发明新的 key 或 value。
"""
import json
import logging
import re
from typing import Dict, List, Any

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

logger = logging.getLogger(__name__)


METADATA_FILTER_PROMPT = ChatPromptTemplate.from_template(
    """
<|system|>
你是一个元数据过滤提取器。根据用户查询，从给定的元数据 schema 中提取需要用于检索前过滤的键值对。

**必须遵守：**
1. 只使用提供的 keys 与候选 values，禁止臆造。
2. 只有当用户明确提到或强烈暗示某个值时，才添加过滤；不确定就不要过滤。
3. 输出 JSON，格式：{{"filters": [{{"key": "...", "values": ["..."]}}]}}。无过滤时输出 {{"filters": []}}。
4. 不要添加与查询无关的过滤条件。
5. 同一 key 可包含多个允许值。
6. **重要：直接返回 JSON 对象，不要包含 ```json 或其他 Markdown 标记。**

可用元数据：
{metadata_schema}

<|user|>
用户查询: {query}
<|assistant|>
请只返回纯 JSON 对象，不要使用代码块标记：
"""
)


class MetadataFilterExtractor:
    def __init__(self, model_name: str, max_tokens: int, api_key: str, base_url: str | None = None):
        self.llm = ChatOpenAI(
            model=model_name,
            temperature=0,
            max_tokens=max_tokens, # type: ignore
            api_key=api_key,
            base_url=base_url or None
        )
    
    def _extract_json_from_response(self, text: str) -> str:
        """
        Extract JSON from LLM response that may be wrapped in markdown code blocks.
        
        Args:
            text: Raw LLM response text
            
        Returns:
            Cleaned JSON string
        """
        # Remove markdown code blocks if present
        text = text.strip()
        
        # Pattern 1: ```json\n{...}\n```
        json_block_pattern = r'```(?:json)?\s*\n?(.*?)\n?```'
        match = re.search(json_block_pattern, text, re.DOTALL)
        if match:
            return match.group(1).strip()
        
        # Pattern 2: Direct JSON (no markdown)
        # Try to find JSON object boundaries
        json_pattern = r'\{.*\}'
        match = re.search(json_pattern, text, re.DOTALL)
        if match:
            return match.group(0).strip()
        
        return text.strip()

    def extract_filters(self, query: str, metadata_catalog: Dict[str, List[str]]) -> List[Dict[str, Any]]:
        """
        Use LLM to extract metadata filters.

        Args:
            query: user original query
            metadata_catalog: mapping of key -> list of candidate values

        Returns:
            list of {"key": str, "values": List[str]}
        """
        if not metadata_catalog:
            return []

        # Truncate candidate values to keep prompt short
        schema_lines = []
        for key, values in metadata_catalog.items():
            sampled = values[:20]
            schema_lines.append(f"- {key}: {', '.join(sampled)}")
        schema = "\n".join(schema_lines)

        prompt = METADATA_FILTER_PROMPT.format(
            metadata_schema=schema,
            query=query
        )
        try:
            response = self.llm.invoke(prompt)
            raw = response.content
            
            # Ensure raw is a string
            if not isinstance(raw, str):
                logger.warning(f"Unexpected response type: {type(raw)}, converting to string")
                raw = str(raw)
            
            # Extract JSON from potential markdown code blocks
            cleaned_json = self._extract_json_from_response(raw)
            logger.debug(f"Raw LLM response: {raw}")
            logger.debug(f"Cleaned JSON: {cleaned_json}")
            
            parsed = json.loads(cleaned_json)
            filters = parsed.get("filters", [])
            if not isinstance(filters, list):
                return []
            # Basic validation: only keep filters with known keys and non-empty values
            sanitized = []
            for f in filters:
                key = f.get("key")
                values = f.get("values", [])
                if key in metadata_catalog and isinstance(values, list) and values:
                    # Ensure values are valid candidates
                    valid_values = [v for v in values if v in metadata_catalog[key]]
                    if valid_values:
                        sanitized.append({"key": key, "values": valid_values})
            logger.info(f"Extracted metadata filters: {sanitized}")
            return sanitized
        except Exception as e:
            logger.warning(f"Metadata filter extraction failed: {e}")
            return []

