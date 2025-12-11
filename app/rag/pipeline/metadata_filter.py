# app/rag/pipeline/metadata_filter.py
"""
LLM-driven metadata expression generator.
Combines the user query, available metadata values, and Milvus reference docs
to produce a ready-to-use boolean expression string for the vector store `expr` field.
"""
import logging
import re
from pathlib import Path
from typing import Dict, List

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

logger = logging.getLogger(__name__)


FILTER_EXPRESSION_PROMPT = ChatPromptTemplate.from_template(
    """
<|system|>
你是一名 Milvus 数据过滤专家。请基于用户问题、可用元数据取值以及官方过滤表达式指南，
生成一个可以直接赋值给 `expr` 的布尔表达式。只有在明确需要过滤时才输出表达式；否则返回 `NONE`。

**指引**
1. 仅使用提供的 metadata 字段：category、dish_name、difficulty。
2. 取值必须来自给定候选，或对字符串使用 LIKE/ILIKE 模糊匹配。
3. 逻辑运算使用 AND/OR/NOT，必要时添加括号。
4. 输出必须是一行纯文本表达式，禁止额外说明、前后缀或 Markdown 代码块。
5. 如果无法确定任何过滤条件，返回 `NONE`。
6. 在用户没有直接且明确要求有关difficulty的过滤时，尽量不要使用difficulty字段。

【Milvus 过滤表达式参考】
{reference_material}

【可用元数据】
{metadata_schema}

<|user|>
用户查询：{query}
<|assistant|>
请输出最终表达式或 `NONE`：
"""
)


REFERENCE_DIR = Path(__file__).resolve().parent / "reference"
REFERENCE_FILES = ("operators.md",)


class MetadataFilterExtractor:
    def __init__(self, model_name: str, max_tokens: int, api_key: str, base_url: str | None = None):
        self.llm = ChatOpenAI(
            model=model_name,
            temperature=0,
            max_tokens=max_tokens,  # type: ignore
            api_key=api_key,
            base_url=base_url or None,
        )
        self.reference_material = self._load_reference_material()

    def build_filter_expression(self, query: str, metadata_catalog: Dict[str, Dict[str, List[str]]]) -> str | None:
        if not metadata_catalog:
            return None

        metadata_schema = self._summarize_metadata(metadata_catalog)
        prompt = FILTER_EXPRESSION_PROMPT.format(
            metadata_schema=metadata_schema,
            reference_material=self.reference_material,
            query=query,
        )
        try:
            response = self.llm.invoke(prompt)
            raw = response.content
            if not isinstance(raw, str):
                logger.warning("LLM response is not string, casting to str.")
                raw = str(raw)

            expression = self._clean_expression(raw)
            logger.info("Generated metadata expression: %s", expression or "NONE")
            return expression
        except Exception as exc:
            logger.warning("Metadata expression generation failed: %s", exc)
            return None

    def _load_reference_material(self) -> str:
        sections: List[str] = []
        for filename in REFERENCE_FILES:
            path = REFERENCE_DIR / filename
            try:
                sections.append(path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                logger.warning("Reference file not found: %s", path)
            except Exception as exc:
                logger.warning("Failed to read reference file %s: %s", path, exc)
        return "\n\n".join(sections)

    @staticmethod
    def _summarize_metadata(metadata_catalog: Dict[str, Dict[str, List[str]]]) -> str:
        lines = []
        for source, metadata in metadata_catalog.items():
            lines.append(f"来源: {source}")
            for key, values in metadata.items():
                sample = "、".join(values)
                lines.append(f"- {key} (共{len(values)}个): {sample}")
        return "\n".join(lines)

    @staticmethod
    def _clean_expression(raw_text: str) -> str | None:
        text = raw_text.strip()
        fence_pattern = r"```(?:[a-zA-Z0-9_+-]+)?\s*([\s\S]*?)```"
        match = re.search(fence_pattern, text)
        if match:
            text = match.group(1).strip()

        if text.startswith("\"") and text.endswith("\"") and len(text) >= 2:
            text = text[1:-1].strip()

        if text.upper() == "NONE" or not text:
            return None

        return text

