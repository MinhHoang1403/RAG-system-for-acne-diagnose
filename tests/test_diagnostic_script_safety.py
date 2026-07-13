from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _text(path: str) -> str:
    return (PROJECT_ROOT / path).read_text(encoding="utf-8")


def test_db_diagnostics_do_not_print_raw_database_url() -> None:
    debug_db = _text("scripts/diagnostics/debug_db.py")
    check_chat_db = _text("scripts/diagnostics/check_chat_db.py")

    assert "print(f\"DB URL: {url}\")" not in debug_db
    assert "print(f\"DB URL: {_mask_url(url)}\")" in debug_db
    assert "print(f\"DB URL: {_mask_url(url)}\")" in check_chat_db


def test_db_diagnostic_writes_require_explicit_opt_in() -> None:
    debug_db = _text("scripts/diagnostics/debug_db.py")
    persist_chat_manual = _text("scripts/diagnostics/persist_chat_manual.py")

    assert "ALLOW_DIAGNOSTIC_WRITES" in debug_db
    assert "ALLOW_DIAGNOSTIC_WRITES" in persist_chat_manual
    assert "Skipping diagnostic write test" in debug_db
    assert "Skipping manual chat persistence" in persist_chat_manual
