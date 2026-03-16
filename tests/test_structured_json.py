from __future__ import annotations

import pytest

from app.utils.structured_json import extract_first_valid_json


def test_extract_first_valid_json_from_code_fence():
    content = "```json\n{\"expr\": \"NONE\"}\n```"
    assert extract_first_valid_json(content) == {"expr": "NONE"}


def test_extract_first_valid_json_from_raw_json():
    assert extract_first_valid_json("{\"a\": 1}") == {"a": 1}


def test_extract_first_valid_json_from_embedded_object():
    content = "prefix... {\"a\": 1, \"b\": 2} ...suffix"
    assert extract_first_valid_json(content) == {"a": 1, "b": 2}


def test_extract_first_valid_json_raises_when_missing():
    with pytest.raises(ValueError):
        extract_first_valid_json("no json here")


def test_extract_first_valid_json_skips_invalid_candidates():
    content = "```json\n{bad}\n```\n\nnoise {bad} more noise {\"ok\": 1}"
    assert extract_first_valid_json(content) == {"ok": 1}
