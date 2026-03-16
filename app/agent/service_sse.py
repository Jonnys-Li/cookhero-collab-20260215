from __future__ import annotations

import json
from typing import Any, Optional

# Default truncate threshold (characters) for SSE payloads.
DEFAULT_TRUNCATE_THRESHOLD = 500
TRUNCATE_SUFFIX = "...[truncated]"

# Do not truncate user input / LLM output.
EXCLUDE_TRUNCATE_KEYS = {"content"}


def truncate_value(
    value: Any,
    threshold: int = DEFAULT_TRUNCATE_THRESHOLD,
    exclude_keys: Optional[set[str]] = None,
    _current_key: Optional[str] = None,
) -> Any:
    """
    Recursively truncate string fields in a nested payload.

    Notes:
    - We intentionally do not truncate `content` to avoid breaking user-visible
      text streams.
    """
    if exclude_keys is None:
        exclude_keys = EXCLUDE_TRUNCATE_KEYS

    if value is None:
        return None

    if isinstance(value, str):
        if _current_key in exclude_keys:
            return value
        if len(value) > threshold:
            return value[:threshold] + TRUNCATE_SUFFIX
        return value

    if isinstance(value, dict):
        return {
            k: truncate_value(v, threshold, exclude_keys, _current_key=k)
            for k, v in value.items()
        }

    if isinstance(value, list):
        return [truncate_value(item, threshold, exclude_keys, _current_key) for item in value]

    return value


def sanitize_value(value: Any) -> Any:
    """
    Convert non-JSON-serializable values to strings.

    This is a last-resort safety net so SSE responses never crash on `json.dumps`.
    """
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {k: sanitize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_value(item) for item in value]
    return str(value)


def format_sse_event(
    event_type: str,
    data: dict,
    truncate_threshold: int = DEFAULT_TRUNCATE_THRESHOLD,
) -> str:
    truncated_data = truncate_value(data, truncate_threshold)
    safe_data = sanitize_value(truncated_data)
    payload = {"type": event_type, **safe_data}
    return f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"

