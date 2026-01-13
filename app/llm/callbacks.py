# app/llm/callbacks.py
"""
LLM usage statistics callback handler.
Captures token usage information from LLM calls and writes to database.
"""

import asyncio
import logging
import threading
import time
from typing import Any, Dict, List, Optional
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from app.llm.context import get_llm_context

logger = logging.getLogger(__name__)


# Background event loop for async database writes
_background_loop: Optional[asyncio.AbstractEventLoop] = None
_background_thread: Optional[threading.Thread] = None


def _get_background_loop() -> asyncio.AbstractEventLoop:
    """Get or create a background event loop for async database operations."""
    global _background_loop, _background_thread

    if _background_loop is None or not _background_loop.is_running():
        _background_loop = asyncio.new_event_loop()
        _background_thread = threading.Thread(
            target=_background_loop.run_forever, daemon=True, name="llm-usage-logger"
        )
        _background_thread.start()

    return _background_loop


class LLMUsageCallbackHandler(BaseCallbackHandler):
    """
    LangChain callback handler for tracking LLM usage statistics.

    Captures token usage information on each LLM call completion
    and asynchronously writes it to the database.

    The context (module_name, user_id, conversation_id) is retrieved
    from contextvars set by the calling module.
    """

    def __init__(self):
        super().__init__()
        self._start_time: Optional[float] = None

    def on_llm_start(
        self,
        serialized: Dict[str, Any],
        prompts: List[str],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """Record the start time when LLM call begins."""
        self._start_time = time.time()
        logger.debug("LLM callback: on_llm_start triggered, run_id=%s", run_id)

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """
        Capture token usage when LLM call completes.

        Extracts token usage from response.llm_output or generation_info,
        then asynchronously writes to database.
        """
        logger.debug("LLM callback: on_llm_end triggered, run_id=%s", run_id)

        duration_ms = (
            int((time.time() - self._start_time) * 1000) if self._start_time else None
        )

        # Get context from contextvars
        ctx = get_llm_context()
        if not ctx:
            logger.debug("LLM callback: No LLM context set, skipping usage logging")
            return

        logger.debug("LLM callback: context found, module=%s", ctx.module_name)

        # Extract token usage
        usage_data = self._extract_usage(response)
        if not usage_data:
            logger.debug("LLM callback: No usage data available in response")

        # Extract model name
        model_name = self._extract_model_name(response)

        # Build log data
        log_data = {
            "request_id": ctx.request_id,
            "module_name": ctx.module_name,
            "user_id": ctx.user_id,
            "conversation_id": ctx.conversation_id,
            "model_name": model_name,
            "input_tokens": (
                usage_data.get("input_tokens") or usage_data.get("prompt_tokens")
                if usage_data
                else None
            ),
            "output_tokens": (
                usage_data.get("output_tokens") or usage_data.get("completion_tokens")
                if usage_data
                else None
            ),
            "total_tokens": usage_data.get("total_tokens") if usage_data else None,
            "duration_ms": duration_ms,
        }

        # Async write to database (non-blocking)
        # Use background event loop since LangChain callbacks are synchronous
        try:
            loop = _get_background_loop()
            logger.debug(
                "LLM callback: scheduling write to background loop, module=%s",
                log_data.get("module_name"),
            )
            future = asyncio.run_coroutine_threadsafe(
                self._write_usage_log(log_data), loop
            )

            # Add a callback to log any errors
            def on_done(fut):
                try:
                    fut.result()  # This will raise any exception that occurred
                    logger.debug("LLM callback: write completed successfully")
                except Exception as e:
                    logger.error("LLM callback: write failed: %s", e, exc_info=True)

            future.add_done_callback(on_done)
        except Exception as e:
            logger.warning(
                "Failed to schedule LLM usage logging: %s, data: %s",
                e,
                log_data.get("module_name"),
            )

    def _extract_usage(self, response: LLMResult) -> Optional[Dict[str, int]]:
        """Extract token usage from LLMResult."""
        # Method 1: From llm_output (OpenAI style)
        if response.llm_output:
            token_usage = response.llm_output.get("token_usage")
            if token_usage:
                return token_usage
            # Some models put usage directly in llm_output
            if "total_tokens" in response.llm_output:
                return response.llm_output

        # Method 2: From generation_info
        if response.generations and response.generations[0]:
            gen = response.generations[0][0]
            if hasattr(gen, "generation_info") and gen.generation_info:
                usage = gen.generation_info.get("usage")
                if usage:
                    return usage

        # Method 3: From response_metadata (newer LangChain)
        if response.generations and response.generations[0]:
            gen = response.generations[0][0]
            if hasattr(gen, "message") and hasattr(gen.message, "usage_metadata"):  # type: ignore
                metadata = gen.message.usage_metadata  # type: ignore
                if metadata:
                    return {
                        "input_tokens": metadata.get("input_tokens"),
                        "output_tokens": metadata.get("output_tokens"),
                        "total_tokens": metadata.get("total_tokens"),
                    }

        return None

    def _extract_model_name(self, response: LLMResult) -> Optional[str]:
        """Extract model name from LLMResult."""
        # Method 1: From llm_output
        if response.llm_output:
            model = response.llm_output.get("model_name") or response.llm_output.get(
                "model"
            )
            if model:
                return model

        # Method 2: From generation_info
        if response.generations and response.generations[0]:
            gen = response.generations[0][0]
            if hasattr(gen, "generation_info") and gen.generation_info:
                model = gen.generation_info.get(
                    "model_name"
                ) or gen.generation_info.get("model")
                if model:
                    return model

        # Method 3: From message.response_metadata
        if response.generations and response.generations[0]:
            gen = response.generations[0][0]
            if hasattr(gen, "message") and hasattr(gen.message, "response_metadata"): # type: ignore
                metadata = gen.message.response_metadata # type: ignore
                if metadata:
                    model = metadata.get("model_name") or metadata.get("model")
                    if model:
                        return model

        return None

    async def _write_usage_log(self, log_data: Dict[str, Any]) -> None:
        """Asynchronously write usage log to database using background session."""
        try:
            import uuid
            from app.database.session import get_background_session_context
            from app.database.models import LLMUsageLogModel

            async with get_background_session_context() as session:
                log = LLMUsageLogModel(
                    id=uuid.uuid4(),
                    request_id=log_data["request_id"],
                    module_name=log_data["module_name"],
                    user_id=log_data.get("user_id"),
                    conversation_id=uuid.UUID(log_data["conversation_id"])
                    if log_data.get("conversation_id")
                    else None,
                    model_name=log_data.get("model_name"),
                    input_tokens=log_data.get("input_tokens"),
                    output_tokens=log_data.get("output_tokens"),
                    total_tokens=log_data.get("total_tokens"),
                    duration_ms=log_data.get("duration_ms"),
                )
                session.add(log)
                # Commit is handled by context manager

            logger.debug(
                "LLM usage logged: module=%s, tokens=%s",
                log_data.get("module_name"),
                log_data.get("total_tokens"),
            )
        except Exception as e:
            logger.error("Failed to write LLM usage log: %s", e, exc_info=True)


# Global singleton instance
llm_usage_callback = LLMUsageCallbackHandler()


def get_usage_callbacks() -> List[BaseCallbackHandler]:
    """
    Get the list of callbacks for LLM usage tracking.

    Returns:
        List containing the LLMUsageCallbackHandler singleton
    """
    return [llm_usage_callback]
