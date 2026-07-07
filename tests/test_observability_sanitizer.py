from __future__ import annotations

from src.observability.trace_exporter import sanitize_for_observability


def test_sanitizer_redacts_secret_like_keys():
    sanitized = sanitize_for_observability(
        {
            "api_key": "abc",
            "nested": {
                "Authorization": "Bearer secret",
                "safe": "value",
            },
            "cookie_value": "session",
        }
    )

    assert sanitized["api_key"] == "[REDACTED]"
    assert sanitized["nested"]["Authorization"] == "[REDACTED]"
    assert sanitized["nested"]["safe"] == "value"
    assert sanitized["cookie_value"] == "[REDACTED]"


def test_sanitizer_truncates_long_text():
    sanitized = sanitize_for_observability({"text": "x" * 20}, max_text_chars=5)

    assert sanitized["text"].startswith("xxxxx")
    assert "truncated 15 chars" in sanitized["text"]
