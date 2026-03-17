"""
Helpers to build `nutrition_snapshot` payloads for Community posts.

The Community module already supports storing an arbitrary JSON payload as
`nutrition_snapshot`. We keep the shape small and stable so that frontends can
render it safely and older clients can ignore unknown fields.
"""

from __future__ import annotations

from typing import Any, Optional


def build_weekly_nutrition_snapshot(
    *,
    weekly_summary: Optional[dict[str, Any]] = None,
    deviation: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    weekly_summary = weekly_summary if isinstance(weekly_summary, dict) else {}
    deviation = deviation if isinstance(deviation, dict) else {}

    snapshot: dict[str, Any] = {
        "kind": "weekly_recap",
        "week_start_date": weekly_summary.get("week_start_date") or deviation.get("week_start_date"),
        "week_end_date": weekly_summary.get("week_end_date"),
        "totals": {
            "actual_calories": weekly_summary.get("total_calories"),
            "actual_protein": weekly_summary.get("total_protein"),
            "actual_fat": weekly_summary.get("total_fat"),
            "actual_carbs": weekly_summary.get("total_carbs"),
            "avg_daily_calories": weekly_summary.get("avg_daily_calories"),
            "plan_calories": deviation.get("total_plan_calories"),
            "deviation_calories": deviation.get("total_deviation"),
            "execution_rate": deviation.get("execution_rate"),
        },
        # Keep this small; the UI can fetch details from diet endpoints if needed.
        "has_plan": bool(deviation.get("has_plan")) if "has_plan" in deviation else None,
        "source": "diet_summary",
        "version": 1,
    }

    # Drop None-ish fields to reduce payload size.
    def _compact(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: _compact(v) for k, v in obj.items() if v is not None}
        if isinstance(obj, list):
            return [_compact(v) for v in obj if v is not None]
        return obj

    return _compact(snapshot)

