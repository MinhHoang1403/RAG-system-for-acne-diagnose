from __future__ import annotations

from scripts import pre_ui_runtime_check


def test_pre_ui_env_summary_redacts_url_credentials(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:secret@localhost:5432/acne")
    monkeypatch.setenv("REDIS_URL", "redis://:secret@localhost:6379/0")

    summary = pre_ui_runtime_check._env_summary()

    assert summary["DATABASE_URL"] == "<CONFIGURED>"
    assert summary["REDIS_URL"] == "<CONFIGURED>"
    assert "secret" not in repr(summary).lower()


def test_pre_ui_frontend_config_has_api_contract():
    result = pre_ui_runtime_check._check_frontend_config()

    assert result["passed"] is True
    assert result["details"]["uses_vite_api_url"] is True
    assert result["details"]["fallback_local_api"] is True
    assert result["details"]["chat_endpoint"] is True
    assert result["details"]["health_endpoint"] is True
