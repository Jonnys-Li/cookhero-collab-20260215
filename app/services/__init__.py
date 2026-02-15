# app/services/__init__.py
"""Services module for business logic.

Avoid eager imports here to prevent heavyweight side effects (e.g. RAG startup)
when importing a specific submodule like ``app.services.user_service``.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "conversation_service",
    "ConversationService",
    "rag_service_instance",
    "RAGService",
]


def __getattr__(name: str) -> Any:
    if name in {"conversation_service", "ConversationService"}:
        from app.services.conversation_service import (
            conversation_service,
            ConversationService,
        )

        mapping = {
            "conversation_service": conversation_service,
            "ConversationService": ConversationService,
        }
        return mapping[name]

    if name in {"rag_service_instance", "RAGService"}:
        from app.services.rag_service import rag_service_instance, RAGService

        mapping = {
            "rag_service_instance": rag_service_instance,
            "RAGService": RAGService,
        }
        return mapping[name]

    raise AttributeError(f"module 'app.services' has no attribute '{name}'")
