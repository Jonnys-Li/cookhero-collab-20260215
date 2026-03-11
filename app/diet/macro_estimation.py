"""
Macro estimation (AUTO) for dishes/meals.

This module must remain free of LangChain/LLM dependencies so it can be used as
a deterministic fallback in demo and test environments.
"""

from __future__ import annotations

from typing import Any, Optional


AUTO_NUTRITION_SOURCE = "AUTO"
AUTO_NUTRITION_CONFIDENCE = 0.35

GOAL_MACRO_RATIOS: dict[str, dict[str, float]] = {
    # ratio = share of calories
    "fat_loss": {"protein": 0.30, "fat": 0.25, "carbs": 0.45},
    "maintenance": {"protein": 0.25, "fat": 0.30, "carbs": 0.45},
    "muscle_gain": {"protein": 0.25, "fat": 0.25, "carbs": 0.50},
    "recovery": {"protein": 0.25, "fat": 0.30, "carbs": 0.45},  # same as maintenance
}


def _normalize_goal(value: Any) -> str:
    goal = str(value or "").strip().lower()
    return goal if goal in GOAL_MACRO_RATIOS else "maintenance"


def estimate_macros_from_calories(calories: int, goal: str) -> dict[str, Optional[float] | str]:
    """Estimate protein/fat/carbs grams from calories and a high-level goal.

    Returns:
        dict with keys:
          - protein_g / fat_g / carbs_g: float grams (1 decimal) or None if invalid
          - source: "AUTO"
          - confidence: fixed 0.35
    """
    try:
        calories_value = int(calories)
    except (TypeError, ValueError):
        calories_value = 0

    if calories_value <= 0:
        return {
            "protein_g": None,
            "fat_g": None,
            "carbs_g": None,
            "source": AUTO_NUTRITION_SOURCE,
            "confidence": AUTO_NUTRITION_CONFIDENCE,
        }

    ratios = GOAL_MACRO_RATIOS[_normalize_goal(goal)]

    protein_g = round((calories_value * ratios["protein"]) / 4.0, 1)
    fat_g = round((calories_value * ratios["fat"]) / 9.0, 1)
    carbs_g = round((calories_value * ratios["carbs"]) / 4.0, 1)

    return {
        "protein_g": protein_g,
        "fat_g": fat_g,
        "carbs_g": carbs_g,
        "source": AUTO_NUTRITION_SOURCE,
        "confidence": AUTO_NUTRITION_CONFIDENCE,
    }

