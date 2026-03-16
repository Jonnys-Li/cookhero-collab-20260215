from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional


MEAL_PLAN_QUERY_PATTERNS = [
    re.compile(
        r"(周计划|周菜单|周食谱|一周|7天|七天|备餐|饮食计划|餐食计划|meal\s*plan|mealprep)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(饮食|餐食|备餐|菜单|食谱|训练).*(计划|规划|安排|制定|生成|推荐|方案)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(计划|规划|安排|制定|生成|推荐|方案).*(饮食|餐食|备餐|菜单|食谱|训练)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(怎么吃|吃什么|如何备餐).*(一周|7天|七天|计划|方案)",
        re.IGNORECASE,
    ),
]

DIET_LOG_QUERY_PATTERNS = [
    re.compile(
        r"(帮我|帮忙|麻烦)?(记录|记一下|记下|记住|写入|同步).*(饮食管理|饮食|这餐|本餐|早餐|午餐|晚餐|加餐)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(帮我|帮忙|麻烦|请)?(加到|加入|添加|算到|算进|计入|记到|记入|录入|同步|写入).*(饮食管理|饮食|今日|今天|这餐|本餐|早餐|午餐|晚餐|加餐)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(log|track)\b.*\b(meal|food|lunch|dinner|breakfast)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"(记录|记一下|写入).*(卡路里|热量|宏量|宏元素|蛋白|脂肪|碳水)",
        re.IGNORECASE,
    ),
]

DIET_NUTRITION_QUERY_PATTERNS = [
    re.compile(r"(卡路里|热量|能量|大卡|kcal|千卡|千焦|kj|焦耳)", re.IGNORECASE),
    re.compile(r"(宏量|宏元素|蛋白|脂肪|碳水)", re.IGNORECASE),
]

MEAL_TYPE_VALUES = {"breakfast", "lunch", "dinner", "snack"}


def is_meal_plan_query(message: str) -> bool:
    if not message:
        return False
    return any(pattern.search(message) for pattern in MEAL_PLAN_QUERY_PATTERNS)


def is_diet_log_query(message: str) -> bool:
    if not message:
        return False
    return any(pattern.search(message) for pattern in DIET_LOG_QUERY_PATTERNS)


def has_concrete_food_quantity(message: str) -> bool:
    """
    Detect "digits + unit" quantities that are likely tied to food amount.

    Keep this conservative to avoid spamming confirm cards on generic knowledge
    questions or goal/budget numbers.
    """
    if not message:
        return False
    text = str(message)
    return bool(
        re.search(
            r"\d+(?:\.\d+)?\s*(?:g|克|公克|kg|千克|公斤|mg|毫克|ml|mL|毫升|l|L|升|斤|两|份|个|颗|只|块|片|包|碗|杯|勺|条|根)",
            text,
            re.IGNORECASE,
        )
    )


def is_diet_nutrition_query(message: str) -> bool:
    """
    Heuristic to detect simple "food nutrition" questions.

    Used to optionally show a "log this" confirm card even when the user only
    asked for calories/macros, but provided a concrete portion.
    """
    if not message:
        return False
    text = str(message)
    if re.search(r"(预算|目标|上限|剩余|调整|cap)", text, re.IGNORECASE):
        return False
    if not has_concrete_food_quantity(text):
        return False
    return any(pattern.search(text) for pattern in DIET_NUTRITION_QUERY_PATTERNS)


def extract_simple_food_items_from_text(message: str) -> list[dict[str, Any]]:
    """
    Best-effort local parser as a fallback when AI parse fails.

    Supports patterns like:
    - "鸡胸肉 20g"
    - "20g 鸡胸肉"
    """
    if not message:
        return []
    text = str(message)
    patterns = [
        re.compile(
            r"(?P<name>[\u4e00-\u9fffA-Za-z]{1,20})\s*(?P<weight>\d+(?:\.\d+)?)\s*(?:g|克)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?P<weight>\d+(?:\.\d+)?)\s*(?:g|克)\s*(?P<name>[\u4e00-\u9fffA-Za-z]{1,20})",
            re.IGNORECASE,
        ),
    ]
    items: list[dict[str, Any]] = []
    seen: set[tuple[str, float | None]] = set()
    for pattern in patterns:
        for match in pattern.finditer(text):
            name = str(match.group("name") or "").strip()
            weight_raw = match.group("weight")
            weight_g: float | None = None
            if weight_raw:
                try:
                    weight_g = float(weight_raw)
                except (TypeError, ValueError):
                    weight_g = None
            if not name:
                continue
            key = (name, weight_g)
            if key in seen:
                continue
            seen.add(key)
            items.append(
                {
                    "food_name": name,
                    "weight_g": weight_g,
                    "unit": "g" if weight_g else None,
                    "calories": None,
                    "protein": None,
                    "fat": None,
                    "carbs": None,
                }
            )
    return items


def calculate_nutrition_totals(items: list[dict[str, Any]]) -> dict[str, float | None]:
    """
    Sum calories/macros from structured items.

    Guardrail: do NOT treat missing values as 0 for display; return None when no
    reliable values are present for a given field.
    """
    if not items:
        return {"calories": None, "protein": None, "fat": None, "carbs": None}

    def _sum_field(field: str) -> float | None:
        total = 0.0
        seen_any = False
        for item in items:
            if not isinstance(item, dict):
                continue
            raw = item.get(field)
            if raw is None:
                continue
            try:
                value = float(raw)
            except (TypeError, ValueError):
                continue
            if value <= 0:
                continue
            total += value
            seen_any = True
        return total if seen_any else None

    calories = _sum_field("calories")
    calories = float(round(calories)) if calories is not None else None

    return {
        "calories": calories,
        "protein": _sum_field("protein"),
        "fat": _sum_field("fat"),
        "carbs": _sum_field("carbs"),
    }


def format_nutrition_totals_text(
    totals: dict[str, float | None],
    *,
    include_kj: bool = False,
) -> str:
    """
    Format totals as a compact line.

    Example: "约 120 kcal（约 502 kJ） · P 20.0 · F 3.0 · C 1.0"
    """
    calories = totals.get("calories")
    protein = totals.get("protein")
    fat = totals.get("fat")
    carbs = totals.get("carbs")

    has_any = any(v is not None for v in (calories, protein, fat, carbs))
    if not has_any:
        return "热量与宏量营养暂无法可靠估算"

    calories_text = "--" if calories is None else f"{calories:.0f}"
    protein_text = "--" if protein is None else f"{protein:.1f}"
    fat_text = "--" if fat is None else f"{fat:.1f}"
    carbs_text = "--" if carbs is None else f"{carbs:.1f}"

    kj_part = ""
    if include_kj and calories is not None:
        kj_value = calories * 4.184
        kj_part = f"（约 {kj_value:.0f} kJ）"

    return (
        f"约 {calories_text} kcal{kj_part} · "
        f"P {protein_text} · F {fat_text} · C {carbs_text}"
    )


def infer_meal_type_for_log(meal_type: Optional[str], *, now: Optional[datetime] = None) -> str:
    normalized = str(meal_type or "").strip().lower()
    if normalized in MEAL_TYPE_VALUES:
        return normalized

    now = now or datetime.now()
    if now.hour < 10:
        return "breakfast"
    if now.hour < 15:
        return "lunch"
    if now.hour < 21:
        return "dinner"
    return "snack"


def extract_log_items_from_vision_analysis(
    vision_analysis: Optional[dict],
) -> list[dict[str, Any]]:
    if not isinstance(vision_analysis, dict):
        return []
    raw_items = vision_analysis.get("items")
    if not isinstance(raw_items, list):
        return []

    def _safe_float(value: Any) -> float | None:
        if value is None:
            return None
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    def _safe_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    items: list[dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        food_name = str(item.get("food_name") or "").strip()
        if not food_name:
            continue
        items.append(
            {
                "food_name": food_name,
                "weight_g": _safe_float(item.get("weight_g")),
                "unit": str(item.get("unit") or "").strip() or None,
                "calories": _safe_int(item.get("calories")),
                "protein": _safe_float(item.get("protein")),
                "fat": _safe_float(item.get("fat")),
                "carbs": _safe_float(item.get("carbs")),
            }
        )
    return items

