import logging
from typing import List

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from app.config import LLMProviderConfig, settings

logger = logging.getLogger(__name__)

HISTORY_REWRITE_PROMPT_TEMPLATE = """
<|system|>
你是一个智能对话助手。你的任务是将用户的当前问题结合对话历史重写为一个**完整、独立、适合检索**的查询。

**核心规则：**
1. **消解指代**：将"它"、"这个"、"那道菜"、"第一个"等代词替换为具体名称
2. **补充上下文**：如果当前问题依赖前文信息，将必要的上下文信息融入查询
3. **保持简洁**：重写后的查询应该简洁明了，适合向量检索
4. **语义完整**：重写后的查询必须是一个完整的、可独立理解的句子

**示例：**

对话历史：
User: 推荐几道鸡蛋的做法
Assistant: 我推荐以下几道鸡蛋菜品：1. 番茄炒蛋 2. 蒸蛋羹 3. 煎蛋

当前问题: 第一道菜怎么做？
-> 重写后: 番茄炒蛋的详细做法是什么？

对话历史：
User: 红烧肉怎么做
Assistant: 红烧肉的做法是...需要五花肉500g...

当前问题: 需要炖多久？
-> 重写后: 红烧肉需要炖多长时间？

<|user|>
## 对话历史:
{history}

## 当前问题:
{query}
<|assistant|>
只输出1句重写后的查询，禁止添加任何解释:
"""

HISTORY_REWRITE_PROMPT = ChatPromptTemplate.from_template(HISTORY_REWRITE_PROMPT_TEMPLATE)


class QueryRewriter:
    """History-aware query rewriting for conversation-driven retrieval."""

    def __init__(self, llm_config: LLMProviderConfig | None = None):
        self.llm_config = llm_config or settings.llm
        if not self.llm_config.api_key:
            raise ValueError("LLM API key must be provided for query rewriting.")

        self.rewrite_llm = ChatOpenAI(
            model=self.llm_config.model_name,
            temperature=0.0,
            max_tokens=self.llm_config.max_tokens,  # type: ignore
            api_key=self.llm_config.api_key,  # type: ignore
            base_url=self.llm_config.base_url,
        )

    def rewrite_with_history(
        self, current_query: str, history_text: str
    ) -> str:
        if not history_text.strip():
            return current_query

        try:
            chain = HISTORY_REWRITE_PROMPT | self.rewrite_llm | StrOutputParser()
            rewritten = (
                chain.invoke({"history": history_text, "query": current_query}).strip()
            )

            if rewritten and rewritten != current_query:
                logger.info(
                    "query rewrite: '%s' -> '%s'",
                    current_query[:80],
                    rewritten[:80],
                )
                return rewritten

        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Failed to rewrite query with history: %s", exc)

        return current_query
