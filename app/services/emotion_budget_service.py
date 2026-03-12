"""
Emotion budget service.

Provides a deterministic budget routing layer for emotion-support workflows:
- Prefer MCP diet auto-adjust tools when available
- Fallback to local `diet_analysis` tool for stability
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import date
from typing import Any, Optional

from app.agent.registry import AgentHub

logger = logging.getLogger(__name__)

DELTA_TO_EMOTION_LEVEL = {
    50: "low",
    100: "medium",
    150: "high",
}


class EmotionBudgetService:
    """Deterministic today-budget routing service."""

    def _warm_load_diet_auto_adjust_in_background(self) -> None:
        """Best-effort background warm-load for built-in diet_auto_adjust MCP tools.

        This keeps request latency stable: we do not await the load here; we only
        schedule it so subsequent calls can pick MCP-first.
        """
        try:
            provider = AgentHub.get_provider("mcp")
        except Exception:
            return

        try:
            from app.agent.tools.providers.mcp import MCPToolProvider

            if not isinstance(provider, MCPToolProvider):
                return
            if "diet_auto_adjust" not in provider.list_servers():
                return
            asyncio.create_task(provider.load_server_tools("diet_auto_adjust"))
        except Exception:
            # Never block or fail budget flow due to warm-load errors.
            return

    def _list_tools(self, user_id: str) -> list[str]:
        try:
            return AgentHub.list_tools(user_id=user_id)
        except Exception as exc:
            logger.warning("Failed to list tools for user %s: %s", user_id, exc)
            return []

    def _pick_mcp_tool(
        self,
        user_id: str,
        *,
        preferred: str,
        suffix: str,
    ) -> Optional[str]:
        tool_names = self._list_tools(user_id)
        if preferred in tool_names:
            return preferred

        candidates = [
            name
            for name in tool_names
            if name.startswith("mcp_") and name.endswith(f"_{suffix}")
        ]
        if not candidates:
            return None

        candidates.sort()
        return candidates[0]

    def _parse_maybe_json(self, value: Any) -> Any:
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        if isinstance(value, list):
            for item in value:
                parsed = self._parse_maybe_json(item)
                if isinstance(parsed, dict):
                    return parsed
            return value
        return value

    def _normalize_payload(self, value: Any) -> Optional[dict[str, Any]]:
        parsed = self._parse_maybe_json(value)
        if isinstance(parsed, dict):
            return parsed
        return None

    async def _execute_tool(
        self,
        *,
        user_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> tuple[Optional[dict[str, Any]], Optional[str]]:
        try:
            executor = AgentHub.create_tool_executor([tool_name], user_id=user_id)
            result = await executor.execute(tool_name, arguments)
        except Exception as exc:
            logger.warning("Tool execution failed: %s (%s)", tool_name, exc)
            return None, str(exc)

        if not result.success:
            return None, result.error or f"{tool_name} execution failed"

        payload = self._normalize_payload(result.data)
        if payload is None:
            return None, f"{tool_name} returned unsupported payload"
        return payload, None

    def _extract_budget(self, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
        budget = payload.get("budget")
        if isinstance(budget, dict):
            return budget
        if "effective_goal" in payload and "today_adjustment" in payload:
            return payload
        return None

    def _extract_goal_source(self, payload: dict[str, Any], budget: dict[str, Any]) -> Optional[str]:
        source = payload.get("goal_source", budget.get("goal_source"))
        if source is None:
            return None
        source_text = str(source).strip().lower()
        if source_text in {"explicit", "avg7d", "default1800"}:
            return source_text
        return None

    def _extract_goal_seeded(self, payload: dict[str, Any], budget: dict[str, Any]) -> Optional[bool]:
        seeded = payload.get("goal_seeded", budget.get("goal_seeded"))
        if seeded is None:
            return None
        return bool(seeded)

    def _target_date_to_str(self, target_date: Optional[date | str]) -> Optional[str]:
        if target_date is None:
            return None
        if isinstance(target_date, date):
            return target_date.isoformat()
        target_date_str = str(target_date).strip()
        return target_date_str or None

    async def get_today_budget(
        self,
        *,
        user_id: str,
        target_date: Optional[date | str] = None,
    ) -> dict[str, Any]:
        target_date_str = self._target_date_to_str(target_date)
        provider_errors: list[str] = []

        mcp_tool = self._pick_mcp_tool(
            user_id,
            preferred="mcp_diet_auto_adjust_get_today_budget",
            suffix="get_today_budget",
        )
        if not mcp_tool:
            self._warm_load_diet_auto_adjust_in_background()
        if mcp_tool:
            mcp_payload, mcp_error = await self._execute_tool(
                user_id=user_id,
                tool_name=mcp_tool,
                arguments={
                    "user_id": user_id,
                    **({"target_date": target_date_str} if target_date_str else {}),
                },
            )
            if mcp_payload:
                budget = self._extract_budget(mcp_payload)
                if budget is not None:
                    goal_source = self._extract_goal_source(mcp_payload, budget)
                    goal_seeded = self._extract_goal_seeded(mcp_payload, budget)
                    return {
                        "message": mcp_payload.get("message") or "获取当天预算成功",
                        "budget": budget,
                        "used_provider": "mcp",
                        "used_tool": mcp_tool,
                        "goal_source": goal_source,
                        "goal_seeded": goal_seeded,
                        "provider_errors": provider_errors,
                    }
                provider_errors.append(f"{mcp_tool}: payload missing budget")
            elif mcp_error:
                provider_errors.append(f"{mcp_tool}: {mcp_error}")

        local_payload, local_error = await self._execute_tool(
            user_id=user_id,
            tool_name="diet_analysis",
            arguments={
                "action": "get_today_budget",
                **({"target_date": target_date_str} if target_date_str else {}),
            },
        )
        if local_payload:
            budget = self._extract_budget(local_payload)
            if budget is not None:
                goal_source = self._extract_goal_source(local_payload, budget)
                goal_seeded = self._extract_goal_seeded(local_payload, budget)
                return {
                    "message": local_payload.get("message") or "获取当天预算成功",
                    "budget": budget,
                    "used_provider": "local",
                    "used_tool": "diet_analysis",
                    "goal_source": goal_source,
                    "goal_seeded": goal_seeded,
                    "provider_errors": provider_errors,
                }
            provider_errors.append("diet_analysis: payload missing budget")
        elif local_error:
            provider_errors.append(f"diet_analysis: {local_error}")

        raise RuntimeError("当前无法读取预算状态：" + " | ".join(provider_errors))

    async def adjust_today_budget(
        self,
        *,
        user_id: str,
        delta_calories: int,
        reason: Optional[str] = None,
        target_date: Optional[date | str] = None,
        mode: str = "user_select",
    ) -> dict[str, Any]:
        if delta_calories not in DELTA_TO_EMOTION_LEVEL:
            raise ValueError("delta_calories 仅支持 50/100/150")

        target_date_str = self._target_date_to_str(target_date)
        provider_errors: list[str] = []
        safe_reason = reason or "情绪支持自动预算调整"

        mcp_tool = self._pick_mcp_tool(
            user_id,
            preferred="mcp_diet_auto_adjust_auto_adjust_today_budget",
            suffix="auto_adjust_today_budget",
        )
        if not mcp_tool:
            self._warm_load_diet_auto_adjust_in_background()
        if mcp_tool:
            emotion_level = DELTA_TO_EMOTION_LEVEL[delta_calories]
            mcp_payload, mcp_error = await self._execute_tool(
                user_id=user_id,
                tool_name=mcp_tool,
                arguments={
                    "user_id": user_id,
                    "emotion_level": emotion_level,
                    "reason": safe_reason,
                    **({"target_date": target_date_str} if target_date_str else {}),
                },
            )
            if mcp_payload:
                budget = self._extract_budget(mcp_payload) or {}
                applied = mcp_payload.get("applied_delta", budget.get("applied_delta"))
                capped = mcp_payload.get("capped", budget.get("capped", False))
                effective_goal = mcp_payload.get(
                    "effective_goal",
                    budget.get("effective_goal"),
                )
                goal_source = self._extract_goal_source(mcp_payload, budget)
                goal_seeded = self._extract_goal_seeded(mcp_payload, budget)
                return {
                    "message": mcp_payload.get("message") or "自动调整完成",
                    "requested": delta_calories,
                    "applied": applied,
                    "capped": bool(capped),
                    "effective_goal": effective_goal,
                    "goal_source": goal_source,
                    "goal_seeded": goal_seeded,
                    "budget": budget,
                    "used_provider": "mcp",
                    "used_tool": mcp_tool,
                    "mode": mode,
                    "provider_errors": provider_errors,
                }
            if mcp_error:
                provider_errors.append(f"{mcp_tool}: {mcp_error}")

        local_payload, local_error = await self._execute_tool(
            user_id=user_id,
            tool_name="diet_analysis",
            arguments={
                "action": "adjust_today_budget",
                "delta_calories": delta_calories,
                "reason": safe_reason,
                "source": f"emotion_support_{mode}",
                **({"target_date": target_date_str} if target_date_str else {}),
            },
        )
        if local_payload:
            budget = self._extract_budget(local_payload) or {}
            applied = budget.get("applied_delta")
            capped = budget.get("capped", False)
            effective_goal = budget.get("effective_goal")
            goal_source = self._extract_goal_source(local_payload, budget)
            goal_seeded = self._extract_goal_seeded(local_payload, budget)
            return {
                "message": local_payload.get("message") or "当天预算调整完成",
                "requested": delta_calories,
                "applied": applied,
                "capped": bool(capped),
                "effective_goal": effective_goal,
                "goal_source": goal_source,
                "goal_seeded": goal_seeded,
                "budget": budget,
                "used_provider": "local",
                "used_tool": "diet_analysis",
                "mode": mode,
                "provider_errors": provider_errors,
            }

        if local_error:
            provider_errors.append(f"diet_analysis: {local_error}")

        raise RuntimeError("当前无法完成自动预算调整：" + " | ".join(provider_errors))


emotion_budget_service = EmotionBudgetService()
