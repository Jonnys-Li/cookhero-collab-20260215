# app/rag/generation_integration.py
import logging
from typing import List

from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate


logger = logging.getLogger(__name__)

REWRITE_PROMPT_TEMPLATE = """
<|system|>
你是食谱数据库的智能搜索助手。你的任务是将用户的输入优化为一个**清晰、自然且完整**的句子，以便进行语义搜索。

**准则：**
1.  **仅限自然语言：** 不要输出关键词堆砌。重写后的查询必须是一个语法完整的句子或自然的问句（例如"我该如何制作……"或"有哪些……"）。
2.  **严禁幻觉：** 除非用户明确提及，否则不要添加具体的形容词（如"简单的"、"快速的"、"健康的"、"辣的"）。
3.  **澄清但不设限：** 如果查询很模糊（例如"我饿了"），将其重写为请求食物推荐的通用但清晰的句子，除非用户指定，否则不要假设是午餐还是晚餐。
4.  **扩展概念：** 对于推荐类查询，可以适当扩展相关概念以提高检索效果。例如"荤素搭配"可以扩展为"既有肉类又有蔬菜的菜品"。
5.  **保持语气：** 保持礼貌和对话感，与原查询的语言风格相匹配。

**示例：**

-   Original: "我想做点吃的"
    -> Rewritten: "你能推荐一些适合我做的食谱吗？"
    *（解释：将模糊的愿望转化为清晰的推荐请求，没有擅自假设是"晚餐"或"简单"的菜。）*

-   Original: "今晚吃啥？"
    -> Rewritten: "今晚晚餐有什么好的食谱推荐吗？"
    *（解释："今晚"暗示了晚餐场景，将其转化为自然的问句。）*

-   Original: "有鸡蛋和西红柿，能做什么"
    -> Rewritten: "用鸡蛋和西红柿可以做什么菜？"
    *（解释：澄清了利用特定食材烹饪的意图，保留了问句格式。）*

-   Original: "红烧肉做法"
    -> Rewritten: "如何制作红烧肉？"
    *（解释：微调语法使其成为完整的句子，意图保持不变。）*

-   Original: "来点甜的"
    -> Rewritten: "给我看一些关于甜点或甜食的食谱。"
    *（解释：将"甜的"扩展为自然的语义类别"甜点"，并组成完整句子。）*

-   Original: "有什么荤素搭配的家常菜？"
    -> Rewritten: "有哪些既有肉类又有蔬菜的家常菜？"
    *（解释：将"荤素搭配"扩展为"既有肉类又有蔬菜"，使语义更清晰，便于检索。）*

-   Original: "推荐几道清淡的菜"
    -> Rewritten: "有哪些口味清淡、不油腻的菜品？"
    *（解释：将"清淡"扩展为"口味清淡、不油腻"，提高检索准确性。）*

<|user|>
原始的查询: {query}
<|assistant|>
只输出1句重写后的查询，禁止添加前缀/后缀/解释/Markdown/项目符号/标题，禁止多行，仅返回重写后的自然语言查询:
"""
REWRITE_PROMPT = ChatPromptTemplate.from_template(REWRITE_PROMPT_TEMPLATE)


GENERATION_PROMPT_TEMPLATE = """
<|system|>
你是 CookHero，一位友好且专业的烹饪助手。你的目标是提供清晰、有用且充满鼓励的烹饪建议。

**核心指令：**

1.  **分析上下文并过滤噪声：**
    -   仔细检查下方提供的“Recipe & Tip Information”（食谱与技巧信息）。
    -   **忽略**任何与用户具体问题无关的文档或文本片段。**只关注**能直接帮助回答该问题的部分。

2.  **响应策略（按优先级排序）：**
    -   **场景 A：找到相关信息**
        如果上下文中包含相关的食谱或技巧，请**主要**基于该信息构建你的回答。你可以对信息进行整理和总结，使其更易于阅读。
    
    -   **场景 B：未找到相关信息**
        如果提供的上下文为空，或与用户的问题完全无关，**不要拒绝回答**。相反：
        1.  礼貌地告知用户，在他的个人知识库/收藏中没有找到该特定的食谱或技巧。
        2.  **立即提供有用的解决方案**，基于你自己通用的烹饪知识来回答。

3.  **语气与格式：**
    -   语气要带有鼓励性，就像厨房里一位乐于助人的朋友。
    -   使用 Markdown（标题、加粗、列表）使说明清晰易读。

<|user|>
## 问题:
{question}
## Recipe & Tip 信息:
{context}
<|assistant|>
"""
GENERATION_PROMPT = ChatPromptTemplate.from_template(GENERATION_PROMPT_TEMPLATE)

# Prompt for rewriting query with chat history context
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

def make_debug_input(invoker_name):
    def debug_input(x):
        print(f"=== {invoker_name} Final Input ===")
        print(x)
        print("======================")
        return x
    return debug_input

class GenerationIntegrationModule:
    """
    Integrates with a Large Language Model (LLM) for rewriting and 
    response generation tasks.
    """

    def __init__(self, model_name: str, temperature: float, max_tokens: int, api_key: str, base_url: str | None = None):
        """
        Initializes the generation module.
        """
        if not api_key or api_key == "None":
            raise ValueError("LLM API key must be provided.")
            
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.api_key = api_key
        self.base_url = base_url
        self.llm = self._init_llm()
        # Dedicated LLM for query rewriting (deterministic)
        self.rewrite_llm = self._init_rewrite_llm()
        
    def _init_llm(self) -> ChatOpenAI:
        """Initializes the Chat LLM."""
        logger.info(f"Initializing LLM: {self.model_name}")
        return ChatOpenAI(
            model=self.model_name,
            temperature=self.temperature,
            max_tokens=self.max_tokens, # type: ignore
            api_key=self.api_key,
            base_url=self.base_url or None
        )

    def _init_rewrite_llm(self) -> ChatOpenAI:
        """Initializes a deterministic LLM for query rewriting."""
        logger.info(f"Initializing rewrite LLM (temperature=0): {self.model_name}")
        return ChatOpenAI(
            model=self.model_name,
            temperature=0.0,
            max_tokens=self.max_tokens,  # type: ignore
            api_key=self.api_key,
            base_url=self.base_url or None
        )

    def rewrite_query(self, query: str) -> str:
        """
        Uses the LLM to rewrite a vague query into a more specific one for better retrieval.
        """
        chain = REWRITE_PROMPT | self.rewrite_llm | StrOutputParser()
        rewritten_query = chain.invoke({"query": query}).strip()
        
        if rewritten_query != query:
            logger.info(f"Query rewritten: '{query}' -> '{rewritten_query}'")
            # fuse the rewritten query back to original if needed
            # rewritten_query = f"Origin User Query: {query}\nAI Rewritten Query: {rewritten_query}"
        else:
            logger.info(f"Query did not require rewriting: '{query}'")
        
        return rewritten_query

    def generate_response(self, query: str, context_docs: List[str], stream: bool = False, temperature: float | None = None):
        """
        Generates a final answer based on the query and a list of context strings.
        
        Args:
            query: The user's query
            context_docs: List of context document strings
            stream: Whether to stream the response
            temperature: Optional temperature override. If provided, temporarily modifies LLM temperature.
        """
        # Temporarily modify temperature if specified
        original_temp = None
        if temperature is not None:
            original_temp = self.llm.temperature
            self.llm.temperature = temperature
            logger.debug(f"Temporarily set LLM temperature to {temperature}")
        
        try:
            context_str = self._build_context_string(context_docs)
            
            chain = (
                {"question": RunnablePassthrough(), "context": lambda _: context_str}
                | GENERATION_PROMPT
                # | RunnableLambda(make_debug_input("generate_response"))
                | self.llm
                | StrOutputParser()
            )
            
            if stream:
                return chain.stream(query)
            else:
                return chain.invoke(query)
        finally:
            # Restore original temperature if it was modified
            if original_temp is not None:
                self.llm.temperature = original_temp
                logger.debug(f"Restored LLM temperature to {original_temp}")
            
    def _build_context_string(self, docs: List[str]) -> str:
        """
        Builds a formatted, structured string from the list of context strings.
        """
        if not docs:
            return "No relevant information found."
        
        context_parts = []
        for i, doc_content in enumerate(docs):
            header = f"--- Context Document [{i+1}] ---\n\n"
            content = doc_content
            
            doc_str = header + content + "\n"
            context_parts.append(doc_str)
            
        return "\n".join(context_parts)

    def rewrite_query_with_history(self, current_query: str, chat_history: List[dict]) -> str:
        """
        Rewrite the current query based on chat history to resolve references.
        
        This handles cases like:
        - "给出第一个菜品的详细做法" -> "番茄炒蛋的详细做法"
        - "这道菜需要多长时间" -> "红烧肉需要多长时间"
        
        Args:
            current_query: The user's current question
            chat_history: List of previous messages [{"role": "user/assistant", "content": "..."}]
            
        Returns:
            A rewritten query that is self-contained and suitable for retrieval
        """
        if not chat_history:
            return current_query
        
        # Format chat history for the prompt
        history_parts = []
        for msg in chat_history[-6:]:  # Last 6 messages for context (3 turns)
            role = "User" if msg.get("role") == "user" else "Assistant"
            content = msg.get("content", "")
            # Truncate long messages
            if len(content) > 500:
                content = content[:500] + "..."
            history_parts.append(f"{role}: {content}")
        
        history_str = "\n".join(history_parts)
        
        try:
            chain = HISTORY_REWRITE_PROMPT | self.rewrite_llm | StrOutputParser()
            rewritten = chain.invoke({
                "history": history_str,
                "query": current_query
            }).strip()
            
            if rewritten and rewritten != current_query:
                logger.info(f"Query rewritten with history: '{current_query}' -> '{rewritten}'")
                return rewritten
            
        except Exception as e:
            logger.warning(f"Failed to rewrite query with history: {e}")
        
        return current_query