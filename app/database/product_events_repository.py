"""
Product events repository.

Stores lightweight product analytics events for debugging and iteration loops.
Important: sanitize `props` before persistence to avoid storing secrets.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select

from app.database.models import ProductEventModel
from app.database.session import get_session_context


_SENSITIVE_KEY_FRAGMENTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "access_token",
    "refresh_token",
    "jwt",
    "bearer",
    "cookie",
)


def _is_sensitive_key(key: str) -> bool:
    lowered = (key or "").strip().lower()
    if not lowered:
        return False
    return any(fragment in lowered for fragment in _SENSITIVE_KEY_FRAGMENTS)


def sanitize_props(value: Any, *, _depth: int = 0) -> Any:
    """
    Sanitize a JSON-like object by masking sensitive keys recursively.

    This is intentionally conservative: if a key looks sensitive, we mask it.
    """
    if _depth > 10:
        return "***TRUNCATED***"

    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for k, v in value.items():
            key = str(k)
            if _is_sensitive_key(key):
                result[key] = "***MASKED***"
                continue
            result[key] = sanitize_props(v, _depth=_depth + 1)
        return result

    if isinstance(value, list):
        # Avoid unbounded payloads.
        if len(value) > 2000:
            value = value[:2000]
        return [sanitize_props(item, _depth=_depth + 1) for item in value]

    # Keep primitive values as-is.
    return value


class ProductEventsRepository:
    async def create_event(
        self,
        *,
        user_id: Optional[str],
        event_name: str,
        props: Optional[dict[str, Any]] = None,
        session_id: Optional[str] = None,
        path: Optional[str] = None,
        client_ts: Optional[datetime] = None,
    ) -> dict:
        safe_props: Optional[dict[str, Any]] = None
        if isinstance(props, dict) and props:
            safe_props = sanitize_props(props)

        event = ProductEventModel(
            user_id=str(user_id) if user_id is not None else None,
            event_name=str(event_name),
            props=safe_props,
            session_id=str(session_id) if session_id else None,
            path=str(path) if path else None,
            client_ts=client_ts,
        )

        async with get_session_context() as session:
            session.add(event)
            # Ensure `id` is available for responses
            await session.flush()

        return event.to_dict()

    async def list_recent_events(
        self,
        *,
        user_id: str,
        limit: int = 50,
    ) -> list[dict]:
        bounded = max(1, min(int(limit), 200))
        async with get_session_context() as session:
            result = await session.execute(
                select(ProductEventModel)
                .where(ProductEventModel.user_id == str(user_id))
                .order_by(ProductEventModel.created_at.desc(), ProductEventModel.id.desc())
                .limit(bounded)
            )
            items = list(result.scalars().all())
        return [item.to_dict() for item in items]


product_events_repository = ProductEventsRepository()

