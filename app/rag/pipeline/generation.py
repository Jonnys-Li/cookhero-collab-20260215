# app/rag/generation_integration.py
import logging
from typing import List

from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from langchain_openai import ChatOpenAI

from app.rag.pipeline.prompts import (
    REWRITE_PROMPT,
    GENERATION_PROMPT,
)

logger = logging.getLogger(__name__)

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