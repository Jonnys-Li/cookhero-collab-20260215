import logging
from typing import List

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from app.config import LLMProviderConfig, settings

logger = logging.getLogger(__name__)

HISTORY_REWRITE_PROMPT_TEMPLATE = """
<|system|>
你是食谱数据库的智能搜索助手。你的任务是将用户的当前问题结合对话历史，重写为一个**完整、独立、自然且适合语义检索**的查询。

**核心规则：**

1. **消解指代**：将"它"、"这个"、"那道菜"、"第一个"等代词替换为具体名称（基于对话历史）

2. **补充上下文**：如果当前问题依赖前文信息，将必要的上下文信息融入查询

3. **仅限自然语言**：输出必须是语法完整的句子或自然的问句（如"如何制作……"、"有哪些……"），不要输出关键词堆砌

4. **扩展概念**：对于推荐类查询，可以适当扩展相关概念以提高检索效果
   - 例如："荤素搭配" → "既有肉类又有蔬菜的菜品"
   - 例如："清淡" → "口味清淡、不油腻"

5. **严禁幻觉**：除非用户明确提及，否则不要添加具体的形容词（如"简单的"、"快速的"、"健康的"、"辣的"）

6. **澄清但不设限**：如果查询模糊（如"我饿了"），将其重写为清晰的通用请求，不要擅自假设具体场景

7. **保持语气**：保持礼貌和对话感，与原查询的语言风格相匹配

**示例：**

场景1（有对话历史）：
对话历史：
User: 推荐几道鸡蛋的做法
Assistant: 我推荐以下几道鸡蛋菜品：1. 番茄炒蛋 2. 蒸蛋羹 3. 煎蛋

当前问题: 第一道菜怎么做？
-> 重写后: 番茄炒蛋的详细做法是什么？

场景2（有对话历史）：
对话历史：
User: 红烧肉怎么做
Assistant: 红烧肉的做法是...需要五花肉500g...

当前问题: 需要炖多久？
-> 重写后: 红烧肉需要炖多长时间？

场景3（无对话历史）：
对话历史: 无

当前问题: 我想做点吃的
-> 重写后: 你能推荐一些适合我做的食谱吗？

场景4（无对话历史）：
对话历史: 无

当前问题: 今晚吃啥？
-> 重写后: 今晚晚餐有什么好的食谱推荐吗？

场景5（无对话历史）：
对话历史: 无

当前问题: 有什么荤素搭配的家常菜？
-> 重写后: 有哪些既有肉类又有蔬菜的家常菜？

场景6（无对话历史）：
对话历史: 无

当前问题: 推荐几道清淡的菜
-> 重写后: 有哪些口味清淡、不油腻的菜品？

<|user|>
## 对话历史:
{history}

## 当前问题:
{query}
<|assistant|>
只输出1句重写后的查询，禁止添加前缀/后缀/解释/Markdown/项目符号/标题，禁止多行，仅返回重写后的自然语言查询:
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
