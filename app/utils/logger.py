from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any


_TRUTHY = {"1", "true", "yes", "y", "on"}


class JsonFormatter(logging.Formatter):
    """Minimal JSON formatter suitable for log aggregation."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        # Preserve a few common context keys when callers use `logger.info(..., extra=...)`.
        for key in ("request_id", "user_id", "session_id", "conversation_id"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)

        return json.dumps(payload, ensure_ascii=False)


def _is_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in _TRUTHY


def configure_logging() -> None:
    """Configure root logging.

    Defaults:
    - Local/dev: human-readable text logs.
    - Render/production: JSON logs by default (can be overridden).

    Environment:
    - LOG_LEVEL: e.g. INFO (default), DEBUG, WARNING
    - LOG_FORMAT: "json" or "text"
    - JSON_LOGS: truthy to force JSON (useful if the platform doesn't set RENDER)
    """
    level_name = (os.getenv("LOG_LEVEL") or "INFO").strip().upper()
    level = getattr(logging, level_name, logging.INFO)

    format_env = (os.getenv("LOG_FORMAT") or "").strip().lower()
    json_default = bool(os.getenv("RENDER")) or _is_truthy(os.getenv("JSON_LOGS"))
    use_json = format_env == "json" or (json_default and format_env != "text")

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(
        JsonFormatter()
        if use_json
        else logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
    )

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = [handler]

