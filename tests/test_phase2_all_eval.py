from __future__ import annotations

import subprocess

from scripts import eval_phase2_all


def test_phase2_all_eval_command_list_never_uses_live_chat():
    flattened = " ".join(" ".join(command) for command in eval_phase2_all.CHECKS)

    assert "--live-chat" not in flattened
    assert "--mode offline" in flattened
    assert "ingest_knowledge.py" not in flattened


def test_phase2_all_eval_summary_with_mocked_subprocess(monkeypatch):
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout='{"passed": true}', stderr="")

    monkeypatch.setattr(eval_phase2_all.subprocess, "run", fake_run)

    summary = eval_phase2_all.run_phase2_all(timeout_seconds=1)

    assert summary["passed"] is True
    assert summary["total_checks"] == len(eval_phase2_all.CHECKS)
    assert summary["failed_checks"] == 0
