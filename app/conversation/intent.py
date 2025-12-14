import json
import logging
from enum import Enum
from typing import Tuple

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from app.config import LLMProviderConfig, settings

logger = logging.getLogger(__name__)


class QueryIntent(Enum):
    """Enum representing the detected intent of a user query."""
    RECIPE_SEARCH = "recipe_search"
    COOKING_TIPS = "cooking_tips"
    INGREDIENT_INFO = "ingredient_info"
    GENERAL_CHAT = "general_chat"
    RECOMMENDATION = "recommendation"


INTENT_DETECTION_PROMPT_TEMPLATE = """
<|system|>
你是一个烹饪助手的意图分类器。你的任务是判断用户的问题是否需要查询食谱知识库。

**分类规则：**

1. **需要查询知识库的情况** (返回 need_rag: true)：
   - 询问具体菜品的做法（如"红烧肉怎么做"）
   - 询问烹饪技巧或方法（如"如何让肉更嫩"）
   - 基于食材询问能做什么菜（如"有鸡蛋能做什么"）
   - 请求推荐菜品（如"晚餐吃什么"）
   - 询问食材处理方法（如"牛肉怎么腌制"）
   - 询问厨房相关知识（如"需要准备什么厨具"）

2. **不需要查询知识库的情况** (返回 need_rag: false)：
   - 简单的问候（如"你好"、"谢谢"）
   - 与烹饪无关的闲聊（如"今天天气怎么样"）
   - 询问助手的能力（如"你能做什么"）
   - 确认性回复（如"好的"、"明白了"）

**输出格式：**
仅返回一个 JSON 对象，格式如下：
{{"need_rag": true/false, "intent": "intent_type", "reason": "简短理由"}}

intent_type 可选值：recipe_search, cooking_tips, ingredient_info, recommendation, general_chat

<|user|>
用户问题: {query}
<|assistant|>
"""

INTENT_DETECTION_PROMPT = ChatPromptTemplate.from_template(INTENT_DETECTION_PROMPT_TEMPLATE)


class IntentDetector:
    """
    Detects user intent to determine if RAG retrieval is needed.
    """

    def __init__(
        self,
        llm_config: LLMProviderConfig | None = None,
        max_tokens: int = 256,
    ):
        """Initialize the intent detector with global or overridden LLM config."""
        self.llm_config = llm_config or settings.llm
        self.llm = ChatOpenAI(
            model=self.llm_config.model_name,
            temperature=0.0,  # Deterministic for classification
            max_completion_tokens=max_tokens,
            api_key=self.llm_config.api_key,  # type: ignore
            base_url=self.llm_config.base_url,
        )
        self.chain = INTENT_DETECTION_PROMPT | self.llm | StrOutputParser()
        logger.info(
            "IntentDetector initialized with model: %s", self.llm_config.model_name
        )

    def detect(self, query: str) -> Tuple[bool, QueryIntent, str]:
        """
        Detect if the query needs RAG retrieval.

        Args:
            query: The user's input query.

        Returns:
            Tuple of (need_rag, intent, reason)
        """
        try:
            response = self.chain.invoke({"query": query})
            content = response.strip()

            # Parse JSON response
            # Handle potential markdown code blocks
            if content.startswith("```"):
                content = content.split("```", 1)[1]
                if content.startswith("json"):
                    content = content[4:]

            result = json.loads(content)
            need_rag = result.get("need_rag", True)
            intent_str = result.get("intent", "general_chat")
            reason = result.get("reason", "")

            # Map string to enum
            intent_map = {
                "recipe_search": QueryIntent.RECIPE_SEARCH,
                "cooking_tips": QueryIntent.COOKING_TIPS,
                "ingredient_info": QueryIntent.INGREDIENT_INFO,
                "recommendation": QueryIntent.RECOMMENDATION,
                "general_chat": QueryIntent.GENERAL_CHAT,
            }
            intent = intent_map.get(intent_str, QueryIntent.GENERAL_CHAT)

            logger.info(
                "Intent detected: need_rag=%s, intent=%s, reason=%s",
                need_rag,
                intent.value,
                reason,
            )
            return need_rag, intent, reason

        except Exception as e:
            logger.warning(
                "Intent detection failed: %s. Defaulting to RAG enabled.", e
            )
            # Default to using RAG when detection fails
            return True, QueryIntent.GENERAL_CHAT, "Detection failed, using default"
