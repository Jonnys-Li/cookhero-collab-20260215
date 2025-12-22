from typing import AsyncGenerator, List

from langchain_core.messages import BaseMessage

from app.config import settings, LLMType
from app.llm import ChatOpenAIProvider
from app.llm.provider import DynamicChatInvoker


class LLMOrchestrator:
    """Handles LLM invocation and streaming responses."""

    def __init__(
        self,
        llm_type: LLMType | str = LLMType.NORMAL,
        provider: ChatOpenAIProvider | None = None,
        ):
            self._llm_type = llm_type
            self._provider = provider or ChatOpenAIProvider(settings.llm)
            _base_llm = self._provider.create_base_llm(llm_type, streaming=True)
            self._llm = DynamicChatInvoker(self._provider, llm_type, _base_llm)

    async def stream(
        self, messages: List[BaseMessage]
    ) -> AsyncGenerator[str, None]:
        async for chunk in self._llm.astream(messages):
            if chunk.content:
                yield str(chunk.content)
