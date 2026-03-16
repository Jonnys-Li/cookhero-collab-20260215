from __future__ import annotations

import logging

from app.security.sanitizer import SensitiveDataFilter, Sanitizer


def test_sensitive_data_filter_sanitizes_format_args():
    filt = SensitiveDataFilter()

    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="token: %s",
        args=("sk-abcdefghijklmnopqrstuvwxyz",),
        exc_info=None,
    )
    assert filt.filter(record) is True
    assert "***MASKED***" in record.msg
    assert record.args == ()


def test_sensitive_data_filter_sanitizes_inline_kv_and_bearer_and_email():
    filt = SensitiveDataFilter()

    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="password=123 bearer abcdefghijklmnopqrstuvwxyz user=a@example.com",
        args=(),
        exc_info=None,
    )
    filt.filter(record)
    assert "password" in record.msg.lower()
    assert "***MASKED***" in record.msg
    assert "bearer" in record.msg.lower()
    assert "***" in record.msg  # masked email includes ***


def test_sensitive_data_filter_sanitizes_dict_args_without_breaking():
    filt = SensitiveDataFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg={"event": "x"},
        args={"password": "p1", "nested": {"token": "t1"}},
        exc_info=None,
    )
    filt.filter(record)
    assert record.args["password"] == "***MASKED***"
    assert record.args["nested"]["token"] == "***MASKED***"


def test_sanitizer_masks_and_truncates_fields():
    data = {
        "password": "secret",
        "access_token": "tok",
        "content": "x" * 600,
        "ok": "y",
    }
    masked = Sanitizer.mask_sensitive_fields(data)
    assert masked["password"] == "***MASKED***"
    assert masked["access_token"] == "***MASKED***"
    assert masked["ok"] == "y"
    assert masked["content"].startswith("x" * 50)
    assert "truncated" in masked["content"]


def test_sanitizer_mask_api_key_is_human_readable():
    assert Sanitizer.mask_api_key("sk-1234567890abcdef") == "sk-12...def"
    assert Sanitizer.mask_api_key("") == "***"
