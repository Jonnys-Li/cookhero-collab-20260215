"""
Meta endpoints.

Purpose:
- Provide lightweight capability probing so the frontend can safely enable/disable
  optional features when the backend is on an older deployment.
"""

from fastapi import APIRouter

from app.community.constants import COMMUNITY_AI_MODES

router = APIRouter()


@router.get("/meta/capabilities")
async def get_capabilities() -> dict:
    # Keep payload stable and intentionally small.
    return {
        "api_version": "0.1.0",
        "community_ai_modes": list(COMMUNITY_AI_MODES),
    }

