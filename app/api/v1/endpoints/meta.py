"""
Meta endpoints.

Purpose:
- Provide lightweight capability probing so the frontend can safely enable/disable
  optional features when the backend is on an older deployment.
"""

from fastapi import APIRouter, Request

from app.community.constants import COMMUNITY_AI_MODES

router = APIRouter()

@router.get("/health")
async def health(request: Request) -> dict:
    """
    Lightweight health endpoint.

    Notes:
    - This route intentionally lives at `/api/v1/health` (no extra prefix) because
      our ops scripts and docs use it as a connectivity gate.
    - Auth middleware still applies: unauthenticated requests will be rejected
      by the gateway with 401, which is expected in our smoke scripts.
    """
    db_ready = bool(getattr(request.app.state, "db_ready", False))
    return {"ok": True, "db_ready": db_ready}


@router.get("/meta/capabilities")
async def get_capabilities() -> dict:
    # Keep payload stable and intentionally small.
    return {
        "api_version": "0.1.0",
        "community_ai_modes": list(COMMUNITY_AI_MODES),
    }
