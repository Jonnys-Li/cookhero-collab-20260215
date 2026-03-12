"""
Community module constants.

This module intentionally keeps "community" scope narrow for the thesis:
check-in sharing + empathetic support, rather than a generic forum.
"""

from __future__ import annotations


DEFAULT_POST_TYPE = "check_in"
REACTION_LIKE = "like"

# Default anonymous display name prefix.
ANON_DISPLAY_PREFIX = "匿名小厨"

# MVP moods - keep it small and stable for filtering/UI.
ALLOWED_MOODS: set[str] = {
    "happy",
    "neutral",
    "anxious",
    "guilty",
    "tired",
}

# Predefined tag set so we can:
# 1) filter reliably on backend
# 2) constrain LLM output to a controlled vocabulary
ALLOWED_TAGS: list[str] = [
    "减脂",
    "增肌",
    "控糖",
    "外食",
    "高蛋白",
    "低碳",
    "暴食后自责",
    "焦虑",
    "想放弃",
    "求建议",
    "坚持打卡",
]

# Simple "shame/blame" word patterns to block in AI-suggested replies.
# This is intentionally conservative and can be expanded later.
SHAME_WORDS: tuple[str, ...] = (
    "你太差",
    "你怎么这么",
    "没用",
    "废物",
    "活该",
    "自作自受",
    "别吃了",
    "闭嘴",
    "蠢",
)

