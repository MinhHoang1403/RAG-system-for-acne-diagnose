from __future__ import annotations

import subprocess

from scripts import generate_phase2_debug_report


def test_debug_report_generation_with_mocked_checks(tmp_path, monkeypatch):
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout='{"passed": true}', stderr="")

    monkeypatch.setattr(generate_phase2_debug_report.subprocess, "run", fake_run)

    report = generate_phase2_debug_report.generate_phase2_debug_report(output_dir=tmp_path, timeout_seconds=1)

    assert report["passed"] is True
    assert (tmp_path / "phase2_debug_report.json").exists()
    assert (tmp_path / "phase2_debug_report.html").exists()
    assert "reports" not in str(tmp_path)
