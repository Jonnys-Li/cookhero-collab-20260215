from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, AsyncIterator, Protocol, Sequence, List, Optional
from langchain_core.callbacks import BaseCallbackHandler
from langchain_openai import ChatOpenAI

from app.config.llm_config import LLMConfig, LLMProfileConfig, LLMType


def create_chat_openai(
    *,
    model: str,
    api_key: str,
    base_url: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: Optional[int] = None,
    streaming: bool = False,
    timeout: Optional[int] = None,
    **kwargs: Any,
) -> ChatOpenAI:
    """
    Create a ChatOpenAI instance with the given parameters.

    This is the unified factory function for creating LLM instances.
    Use this instead of directly instantiating ChatOpenAI.

    Args:
        model: Model name
        api_key: API key
        base_url: Base URL for the API (optional)
        temperature: Temperature setting
        max_tokens: Maximum tokens for completion
        streaming: Enable streaming mode
        timeout: Request timeout in seconds
        **kwargs: Additional ChatOpenAI parameters

    Returns:
        ChatOpenAI instance
    """
    llm_kwargs: dict[str, Any] = {
        "model": model,
        "api_key": api_key,
        "temperature": temperature,
        "streaming": streaming,
        **kwargs,
    }

    if base_url:
        llm_kwargs["base_url"] = base_url
    if max_tokens is not None:
        llm_kwargs["max_completion_tokens"] = max_tokens
    if timeout is not None:
        llm_kwargs["timeout"] = timeout

    return ChatOpenAI(**llm_kwargs)


class ModelSelectionStrategy(Protocol):
    def choose(self, model_names: Sequence[str]) -> str: ...


@dataclass(frozen=True)
class RandomChoiceStrategy:
    def choose(self, model_names: Sequence[str]) -> str:
        if not model_names:
            raise ValueError("model_names cannot be empty")
        return random.choice(list(model_names))


@dataclass
class ChatOpenAIProvider:
    llm_config: LLMConfig
    selector: ModelSelectionStrategy = RandomChoiceStrategy()

    def profile(self, llm_type: LLMType | str | None) -> LLMProfileConfig:
        return self.llm_config.get_profile(llm_type)

    def choose_model(self, llm_type: LLMType | str | None) -> str:
        profile = self.profile(llm_type)
        return self.selector.choose(profile.model_names)

    def create_base_llm(
        self,
        llm_type: LLMType | str | None,
        *,
        streaming: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> ChatOpenAI:
        profile = self.profile(llm_type)
        return ChatOpenAI(
            model=profile.pick_default_model(),
            api_key=profile.api_key,  # type: ignore
            base_url=profile.base_url,
            temperature=profile.temperature if temperature is None else temperature,
            max_completion_tokens=profile.max_tokens
            if max_tokens is None
            else max_tokens,
            streaming=streaming,
            **kwargs,
        )

    def bind_for_call(
        self, llm: ChatOpenAI, llm_type: LLMType | str | None
    ) -> ChatOpenAI:
        model = self.choose_model(llm_type)
        return llm.bind(model=model)  # type: ignore

    def create_tracked_invoker(
        self,
        llm_type: LLMType | str | None,
        *,
        streaming: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> "DynamicChatInvoker":
        """
        Create a DynamicChatInvoker with usage tracking callbacks.

        This method creates an invoker that automatically logs token usage
        and other statistics to the database.

        Args:
            llm_type: LLM type (fast/normal)
            streaming: Enable streaming mode
            temperature: Override temperature
            max_tokens: Override max tokens
            **kwargs: Additional ChatOpenAI parameters

        Returns:
            DynamicChatInvoker with usage tracking enabled
        """
        from app.llm.callbacks import get_usage_callbacks

        base_llm = self.create_base_llm(
            llm_type,
            streaming=streaming,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

        return DynamicChatInvoker(
            provider=self,
            llm_type=llm_type,
            base_llm=base_llm,
            callbacks=get_usage_callbacks(),
        )


class DynamicChatInvoker:
    """
    A wrapper to dynamically bind ChatOpenAI model before each call.
    Supports tool binding, callbacks, and other ChatOpenAI methods.
    """

    def __init__(
        self,
        provider: ChatOpenAIProvider,
        llm_type: LLMType | str | None,
        base_llm: ChatOpenAI,
        callbacks: List[BaseCallbackHandler] | None = None,
    ):
        self._provider = provider
        self._llm_type = llm_type
        self._base_llm = base_llm
        self._bound_tools: list[Any] = []  # Store bound tools
        self._tool_choice: Any = None  # Store tool_choice parameter
        self._callbacks: List[BaseCallbackHandler] = callbacks or []  # Store callbacks

    def _bind(self) -> ChatOpenAI:
        """Bind model and tools dynamically."""
        llm = self._provider.bind_for_call(self._base_llm, self._llm_type)

        # If tools were bound, apply them
        if self._bound_tools:
            bind_kwargs: dict[str, Any] = {"tools": self._bound_tools}
            if self._tool_choice is not None:
                bind_kwargs["tool_choice"] = self._tool_choice
            llm = llm.bind(**bind_kwargs)  # type: ignore

        return llm  # type: ignore

    def _build_config(self, kwargs: dict) -> dict:
        """Build RunnableConfig with callbacks for LangChain invocation.

        Uses 'config' parameter with 'callbacks' key which is the proper
        LangChain way to pass callbacks through RunnableBinding objects.
        """
        call_callbacks = kwargs.pop("callbacks", None) or []
        # Also check for config.callbacks pattern
        config = kwargs.pop("config", None) or {}
        if isinstance(config, dict):
            config_callbacks = config.get("callbacks", []) or []
        else:
            config_callbacks = []

        merged = list(call_callbacks) + list(config_callbacks) + self._callbacks
        if merged:
            kwargs["config"] = {"callbacks": merged}
        return kwargs

    async def ainvoke(self, *args: Any, **kwargs: Any) -> Any:
        """Async invoke the LLM with dynamic model binding."""
        kwargs = self._build_config(kwargs)
        return await self._bind().ainvoke(*args, **kwargs)

    def astream(self, *args: Any, **kwargs: Any) -> AsyncIterator[Any]:
        """Stream responses from the LLM with dynamic model binding."""
        kwargs = self._build_config(kwargs)
        return self._bind().astream(*args, **kwargs)