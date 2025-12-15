import json
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

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


@dataclass
class IntentDetectionResult:
    """Structured intent detection result with room for future extensions."""

    need_rag: bool
    intent: QueryIntent
    reason: str
    raw: dict


INTENT_DETECTION_PROMPT_TEMPLATE = """
<|system|>
你是一个烹饪助手的意图分类器。你的任务是结合**当前问题**和**对话历史**，判断是否需要查询知识库，并给出意图分类。

**输入信号：**
- 当前问题：用户最新的一句话
- 对话历史：按时间顺序的多轮对话，可能包含指代、省略或承接

**分类规则（可扩展）：**
1. **需要查询知识库 (need_rag: true)**：
    - 询问具体菜品做法、步骤、时间、技巧
    - 基于食材/场景的菜品推荐或能做什么
    - 烹饪技巧、口味调整、处理方法
    - 厨房准备、器具、时间/温度等操作性问题
2. **不需要查询知识库 (need_rag: false)**：
    - 知识库只有菜品做法和烹饪技巧，其他有关菜品的问题不需要RAG，例如营养价值、历史文化等
    - 闲聊、客套、感谢
    - 与烹饪无关的对话
    - 纯确认、澄清（如“好的”“就这样”）

**输出格式：**
{{"need_rag": true/false, "intent": "intent_type", "reason": "简短理由"}}

你必须输出一个 JSON 对象；请勿使用 Markdown；请勿在 JSON 之外添加任何文本；输出必须是有效的 JSON。

intent_type 可选值：recipe_search, cooking_tips, ingredient_info, recommendation, general_chat

<|user|>
【对话历史】
{history}

【当前问题】
{query}
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
        logger.info("IntentDetector initialized")

    def detect(
        self,
        query: str,
        history_text: Optional[str] = None,
    ) -> IntentDetectionResult:
        """Detect if the query needs RAG retrieval with history awareness.

        Args:
            query: Latest user query.
            history_text: Pre-formatted history text (already concatenated by ContextManager).
        """
        history_str = history_text

        try:
            response = self.chain.invoke({"query": query, "history": history_str})
            content = response.strip()

            if content.startswith("```"):
                content = content.strip("```").strip()
                if content.startswith("json"):
                    content = content[4:].strip()

            result = json.loads(content)
            need_rag = result.get("need_rag", True)
            intent_str = result.get("intent", "general_chat")
            reason = result.get("reason", "")

            intent_map = {
                "recipe_search": QueryIntent.RECIPE_SEARCH,
                "cooking_tips": QueryIntent.COOKING_TIPS,
                "ingredient_info": QueryIntent.INGREDIENT_INFO,
                "recommendation": QueryIntent.RECOMMENDATION,
                "general_chat": QueryIntent.GENERAL_CHAT,
            }
            intent = intent_map.get(intent_str, QueryIntent.GENERAL_CHAT)

            logger.info(
                "intent detected need_rag=%s intent=%s reason=%s",
                need_rag,
                intent.value,
                reason[:120],
            )
            return IntentDetectionResult(
                need_rag=need_rag,
                intent=intent,
                reason=reason,
                raw=result,
            )

        except Exception as exc:
            logger.warning(
                "Intent detection failed: %s. Defaulting to non-RAG mode.", exc
            )
            return IntentDetectionResult(
                need_rag=False,
                intent=QueryIntent.GENERAL_CHAT,
                reason="Detection failed, using default",
                raw={},
            )
