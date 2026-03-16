from __future__ import annotations

import json

from app.agent.service_sse import format_sse_event


def test_format_sse_event_truncates_non_content_fields_but_keeps_content():
    long_text = "x" * 600
    sse = format_sse_event(
        "trace",
        {
            "content": long_text,
            "other": long_text,
        },
        truncate_threshold=100,
    )

    assert sse.startswith("data: ")
    payload = json.loads(sse[len("data: ") :].strip())
    assert payload["type"] == "trace"
    assert payload["content"] == long_text
    assert payload["other"].endswith("...[truncated]")
    assert len(payload["other"]) < len(long_text)

