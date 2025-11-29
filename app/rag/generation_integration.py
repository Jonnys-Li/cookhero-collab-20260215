# app/rag/generation_integration.py
import os
import logging
from typing import List

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.documents import Document
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

class GenerationIntegrationModule:
    """
    Integrates with a Large Language Model (LLM) to generate answers.
    """
    def __init__(self, model_name: str, temperature: float, max_tokens: int, api_key: str, base_url: str | None = None):
        """
        Initializes the generation module.
        Args:
            model_name: The name of the LLM to use (e.g., "gpt-4o-mini").
            temperature: The generation temperature.
            max_tokens: The maximum number of tokens to generate.
            api_key: The OpenAI API key.
        """
        if not api_key or api_key == "None":
            raise ValueError("OpenAI API key must be provided.")
            
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.api_key = api_key
        self.base_url = base_url
        self.llm = self._init_llm()
        
    def _init_llm(self) -> ChatOpenAI:
        """Initializes the Chat LLM."""
        logger.info(f"Initializing LLM: {self.model_name}")
        
        # Using the up-to-date langchain_openai integration
        return ChatOpenAI(
            model=self.model_name,
            temperature=self.temperature,
            max_tokens=self.max_tokens, # type: ignore
            api_key=self.api_key,
            base_url=self.base_url or None
        )
        
    def route_query(self, query: str) -> str:
        """
        Uses the LLM to classify the user's query into predefined categories.
        Args:
            query: The user's query.
        Returns:
            A category string ('list', 'detail', 'general').
        """
        prompt = ChatPromptTemplate.from_template("""
根据用户的问题，将其分类为以下三种类型之一：
1. 'list' - 用户想要获取菜品列表或推荐，只需要菜名。例如：推荐几个素菜、有什么川菜。
2. 'detail' - 用户想要具体的制作方法或详细信息。例如：宫保鸡丁怎么做、制作步骤、需要什么食材。
3. 'general' - 其他一般性问题。例如：什么是川菜、制作技巧、营养价值。

请只返回分类结果：'list'、'detail' 或 'general'.

用户问题: {query}
分类结果:""")
        
        chain = prompt | self.llm | StrOutputParser()
        result = chain.invoke({"query": query}).strip().lower().replace("'", "")
        
        if result in ['list', 'detail', 'general']:
            logger.info(f"Query routed as: '{result}'")
            return result
        
        logger.warning(f"Query router failed to classify, defaulting to 'general'. Raw output: {result}")
        return 'general'

    def rewrite_query(self, query: str) -> str:
        """
        Uses the LLM to rewrite a vague query into a more specific one for better retrieval.
        Args:
            query: The original user query.
        Returns:
            The rewritten query, or the original if no rewrite was needed.
        """
        prompt = ChatPromptTemplate.from_template("""
你是一个智能查询分析助手。请分析用户的查询，判断是否需要重写以提高食谱搜索效果。
如果查询已经足够具体（如包含菜名），则直接返回原查询.
如果查询模糊（如“做个菜”），则将其重写为更具体的搜索词.

重写原则：保持原意，增加烹饪术语，简洁明了.
示例：
- "做菜" -> "简单易做的家常菜谱"
- "推荐个菜" -> "简单家常菜推荐"
- "宫保鸡丁怎么做" -> "宫保鸡丁怎么做"

原始查询: {query}
请只输出最终用于搜索的查询:""")
        
        chain = prompt | self.llm | StrOutputParser()
        rewritten_query = chain.invoke({"query": query}).strip()
        
        if rewritten_query != query:
            logger.info(f"Query rewritten: '{query}' -> '{rewritten_query}'")
        else:
            logger.info(f"Query did not require rewriting: '{query}'")
        
        return rewritten_query

    def generate_response(self, query: str, context_docs: List[Document], stream: bool = False):
        """
        Generates a final answer based on the query and retrieved context.
        Args:
            query: The user's (potentially rewritten) query.
            context_docs: The list of retrieved documents for context.
            stream: Whether to stream the response.
        Returns:
            A string or a streaming generator, depending on the 'stream' flag.
        """
        prompt = ChatPromptTemplate.from_template("""
你是一位专业的烹饪助手。请根据以下食谱信息，为用户的问题提供一个清晰、实用且有条理的回答.
如果提供的信息不足以回答问题，请诚实地说明.

## 用户问题:
{question}

## 相关食谱信息:
{context}

请开始你的回答:""")
        
        context_str = self._build_context_string(context_docs)
        
        chain = (
            {"question": RunnablePassthrough(), "context": lambda _: context_str}
            | prompt
            | self.llm
            | StrOutputParser()
        )
        
        if stream:
            return chain.stream(query)
        else:
            return chain.invoke(query)
            
    def _build_context_string(self, docs: List[Document], max_length: int = 8000) -> str:
        """
        Builds a formatted string from the list of context documents.
        """
        if not docs:
            return "没有找到相关的食谱信息."
        
        context_parts = []
        current_length = 0
        
        for doc in docs:
            dish_name = doc.metadata.get('dish_name', '未知菜品')
            content = doc.page_content
            doc_str = f"--- 食谱: {dish_name} ---\n{content}\n"
            
            if current_length + len(doc_str) > max_length:
                break
                
            context_parts.append(doc_str)
            current_length += len(doc_str)
            
        return "\n".join(context_parts)
