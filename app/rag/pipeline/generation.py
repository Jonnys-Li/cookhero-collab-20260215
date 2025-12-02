# app/rag/generation_integration.py
import logging
from typing import List

from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_openai import ChatOpenAI

from app.rag.pipeline.prompts import (
    ROUTING_PROMPT,
    REWRITE_PROMPT,
    GENERATION_PROMPT,
)

logger = logging.getLogger(__name__)

class GenerationIntegrationModule:
    """
    Integrates with a Large Language Model (LLM) for routing, rewriting,
    and response generation tasks.
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
        
    def _init_llm(self) -> ChatOpenAI:
        """Initializes the Chat LLM."""
        logger.info(f"Initializing LLM: {self.model_name}")
        return ChatOpenAI(
            model=self.model_name,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            api_key=self.api_key,
            base_url=self.base_url or None
        )
        
    def route_query(self, query: str) -> str:
        """
        Uses the LLM to classify the user's query to determine which data source to use.
        """
        chain = ROUTING_PROMPT | self.llm | StrOutputParser()
        result = chain.invoke({"query": query}).strip().lower().replace("'", "")
        
        if result in ['recipes', 'tips']:
            logger.info(f"Query routed to data source: '{result}'")
            return result
        
        logger.warning(f"Query router failed to classify, defaulting to 'recipes'. Raw output: {result}")
        return 'recipes'

    def rewrite_query(self, query: str) -> str:
        """
        Uses the LLM to rewrite a vague query into a more specific one for better retrieval.
        """
        chain = REWRITE_PROMPT | self.llm | StrOutputParser()
        rewritten_query = chain.invoke({"query": query}).strip()
        
        if rewritten_query != query:
            logger.info(f"Query rewritten: '{query}' -> '{rewritten_query}'")
        else:
            logger.info(f"Query did not require rewriting: '{query}'")
        
        return rewritten_query

    def generate_response(self, query: str, context_docs: List[Document], stream: bool = False):
        """
        Generates a final answer based on the query and retrieved context.
        """
        context_str = self._build_context_string(context_docs)
        
        chain = (
            {"question": RunnablePassthrough(), "context": lambda _: context_str}
            | GENERATION_PROMPT
            | self.llm
            | StrOutputParser()
        )
        
        if stream:
            return chain.stream(query)
        else:
            return chain.invoke(query)
            
    def _build_context_string(self, docs: List[Document], max_length: int = 8000) -> str:
        """
        Builds a formatted, structured string from the list of context documents.
        
        Args:
            docs: A list of retrieved Document objects.
            max_length: The approximate maximum character length for the context string.
            
        Returns:
            A single string containing the formatted context, ready for the LLM.
        """
        if not docs:
            return "No relevant information found."
        
        context_parts = []
        current_length = 0
        
        for i, doc in enumerate(docs):
            source = doc.metadata.get('source', 'Unknown Source')
            dish_name = doc.metadata.get('dish_name', 'General Information')
            
            header = f"--- Context Document [{i+1}] ---\nSource: {source}\nTopic: {dish_name}\n\n"
            content = doc.page_content
            
            doc_str = header + content + "\n"
            
            if current_length + len(doc_str) > max_length:
                # If adding the next doc would exceed the limit, stop.
                logger.warning(f"Context length limit ({max_length} chars) reached. Truncating.")
                break
                
            context_parts.append(doc_str)
            current_length += len(doc_str)
            
        return "\n".join(context_parts)
