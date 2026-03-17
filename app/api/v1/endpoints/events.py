"""
Product events endpoints.

These endpoints are used for lightweight product analytics and debugging.

Integration note:
- This module defines `router` but is NOT included in app/main.py by this agent
  to avoid merge conflicts. The integrator should include:

    app.include_router(events.router, prefix=settings.API_V1_STR, tags=["Events"])
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.database.product_events_repository import product_events_repository

router = APIRouter()


def _get_user_id_or_401(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="需要登录")
    return str(user_id)


class CreateEventRequest(BaseModel):
    event_name: str = Field(..., min_length=1, max_length=128)
    props: Optional[dict[str, Any]] = None
    session_id: Optional[str] = Field(default=None, max_length=128)
    path: Optional[str] = Field(default=None, max_length=512)
    client_ts: Optional[datetime] = None


@router.post("/events", status_code=201)
async def create_event(payload: CreateEventRequest, request: Request) -> dict:
    """
    Record a product event.

    Auth:
    - Requires JWT (handled by global auth middleware).
    - `user_id` is taken from request.state.user_id; any client-provided user_id
      should be ignored to prevent spoofing.
    """
    user_id = _get_user_id_or_401(request)
    return await product_events_repository.create_event(
        user_id=user_id,
        event_name=payload.event_name,
        props=payload.props,
        session_id=payload.session_id,
        path=payload.path,
        client_ts=payload.client_ts,
    )


@router.get("/events/recent")
async def list_recent_events(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    """
    Debug endpoint: list recent events for the current user.
    """
    user_id = _get_user_id_or_401(request)
    events = await product_events_repository.list_recent_events(
        user_id=user_id,
        limit=limit,
    )
    return {"events": events}

