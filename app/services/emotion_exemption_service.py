"""
Emotion exemption service.

Stores a same-day "emotion exemption" flag for high-risk emotion sessions so
diet correction and budget-adjust flows can degrade to a safer experience.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, time
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from redis.asyncio import Redis
else:
    Redis = Any

logger = logging.getLogger(__name__)


class EmotionExemptionService:
    """Manage high-risk emotion exemption state."""

    def __init__(self) -> None:
        self._redis: Optional[Redis] = None
        self._memory: dict[str, dict[str, Any]] = {}

    def set_redis(self, redis_client: Redis) -> None:
        self._redis = redis_client

    def _target_date(self, target_date: Optional[date] = None) -> date:
        return target_date or date.today()

    def _expires_at(self, target_date: date) -> datetime:
        return datetime.combine(target_date, time.max).replace(microsecond=0)

    def _ttl_seconds(self, expires_at: datetime) -> int:
        now = datetime.now()
        ttl = int((expires_at - now).total_seconds())
        return max(60, ttl)

    def _redis_key(self, user_id: str, target_date: date) -> str:
        return f"emotion_exemption:{user_id}:{target_date.isoformat()}"

    async def activate(
        self,
        *,
        user_id: str,
        level: str = "high",
        reason: str = "high_risk_emotion",
        target_date: Optional[date] = None,
        source: str = "emotion_support",
        summary: Optional[str] = None,
    ) -> dict[str, Any]:
        actual_date = self._target_date(target_date)
        expires_at = self._expires_at(actual_date)
        payload = {
            "is_active": True,
            "date": actual_date.isoformat(),
            "level": str(level or "high"),
            "reason": str(reason or "high_risk_emotion"),
            "source": str(source or "emotion_support"),
            "summary": str(summary or ""),
            "activated_at": datetime.utcnow().isoformat(),
            "expires_at": expires_at.isoformat(),
        }

        key = self._redis_key(user_id, actual_date)
        ttl_seconds = self._ttl_seconds(expires_at)

        if self._redis:
            try:
                await self._redis.setex(
                    key,
                    ttl_seconds,
                    json.dumps(payload, ensure_ascii=False),
                )
            except Exception as exc:
                logger.warning("Failed to store emotion exemption in Redis: %s", exc)
                self._memory[key] = payload
        else:
            self._memory[key] = payload

        return payload

    async def get_status(
        self,
        *,
        user_id: str,
        target_date: Optional[date] = None,
    ) -> dict[str, Any]:
        actual_date = self._target_date(target_date)
        key = self._redis_key(user_id, actual_date)

        payload: Optional[dict[str, Any]] = None
        if self._redis:
            try:
                raw = await self._redis.get(key)
                if raw:
                    payload = json.loads(raw)
            except Exception as exc:
                logger.warning("Failed to load emotion exemption from Redis: %s", exc)

        if payload is None:
            payload = self._memory.get(key)

        if not isinstance(payload, dict):
            return {
                "is_active": False,
                "date": actual_date.isoformat(),
                "level": None,
                "reason": None,
                "source": None,
                "summary": None,
                "activated_at": None,
                "expires_at": None,
            }

        expires_at = payload.get("expires_at")
        if isinstance(expires_at, str):
            try:
                expires_dt = datetime.fromisoformat(expires_at)
            except ValueError:
                expires_dt = None
            if expires_dt and expires_dt < datetime.now():
                self._memory.pop(key, None)
                return {
                    "is_active": False,
                    "date": actual_date.isoformat(),
                    "level": None,
                    "reason": None,
                    "source": None,
                    "summary": None,
                    "activated_at": None,
                    "expires_at": None,
                }

        return {
            "is_active": bool(payload.get("is_active")),
            "date": str(payload.get("date") or actual_date.isoformat()),
            "level": payload.get("level"),
            "reason": payload.get("reason"),
            "source": payload.get("source"),
            "summary": payload.get("summary"),
            "activated_at": payload.get("activated_at"),
            "expires_at": payload.get("expires_at"),
        }

    async def is_active(
        self,
        *,
        user_id: str,
        target_date: Optional[date] = None,
    ) -> bool:
        status = await self.get_status(user_id=user_id, target_date=target_date)
        return bool(status.get("is_active"))


emotion_exemption_service = EmotionExemptionService()
