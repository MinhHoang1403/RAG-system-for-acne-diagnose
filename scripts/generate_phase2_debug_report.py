#!/usr/bin/env python3
"""Generate an offline Phase 2 debug report as JSON and HTML."""

from __future__ import annotations

import html
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = PROJECT_ROOT / "reports"

REPORT_CHECKS = [
    ["scripts/inspect_phase2_readiness.py"],
    ["scripts/inspect_cache_versions.py"],
    ["scripts/eval_phase2_retrieval.py"],
    ["scripts/eval_phase2_context_packing.py"],
    ["scripts/eval_phase2_reranking.py"],
    ["scripts/eval_phase2_answer_quality.py"],
    ["scripts/smoke_phase2_runtime.py", "--mode", "offline"],
]


def generate_phase2_debug_report(output_dir: Path = REPORT_DIR, timeout_seconds: int = 120) -> dict[str, Any]:
    checks = [_run_check(command, timeout_seconds=timeout_seconds) for command in REPORT_CHECKS]
    passed = all(check["passed"] for check in checks)
    report = {
        "passed": passed,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "phase2_debug_report.json"
    html_path = output_dir / "phase2_debug_report.html"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    html_path.write_text(_render_html(report), encoding="utf-8")
    report["paths"] = {
        "json": str(json_path),
        "html": str(html_path),
    }
    return report


def _run_check(command: list[str], *, timeout_seconds: int) -> dict[str, Any]:
    started = time.perf_counter()
    full_command = [sys.executable, *command]
    try:
        completed = subprocess.run(
            full_command,
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        stdout = completed.stdout.strip()
        return {
            "name": " ".join(command),
            "command": full_command,
            "passed": completed.returncode == 0,
            "returncode": completed.returncode,
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            "summary": _parse_json_or_excerpt(stdout),
            "stderr": completed.stderr.strip()[-1000:] if completed.stderr else "",
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "name": " ".join(command),
            "command": full_command,
            "passed": False,
            "returncode": None,
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            "summary": {"error": f"Timed out after {timeout_seconds}s"},
            "stderr": str(exc),
        }


def _parse_json_or_excerpt(text: str) -> Any:
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"output_excerpt": text[-2000:]}


def _render_html(report: dict[str, Any]) -> str:
    status = "PASS" if report["passed"] else "FAIL"
    rows = []
    for check in report["checks"]:
        check_status = "PASS" if check["passed"] else "FAIL"
        rows.append(
            "<tr>"
            f"<td>{html.escape(check['name'])}</td>"
            f"<td class='{check_status.lower()}'>{check_status}</td>"
            f"<td>{html.escape(str(check.get('duration_ms', '')))}</td>"
            f"<td><pre>{html.escape(json.dumps(check.get('summary', {}), ensure_ascii=False, indent=2, default=str))}</pre></td>"
            "</tr>"
        )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Phase 2 Debug Report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #1f2937; }}
    h1 {{ margin-bottom: 4px; }}
    .pass {{ color: #047857; font-weight: 700; }}
    .fail {{ color: #b91c1c; font-weight: 700; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 18px; }}
    th, td {{ border: 1px solid #d1d5db; padding: 8px; vertical-align: top; }}
    th {{ background: #f3f4f6; text-align: left; }}
    pre {{ white-space: pre-wrap; max-height: 320px; overflow: auto; margin: 0; }}
  </style>
</head>
<body>
  <h1>Phase 2 Debug Report</h1>
  <p>Generated at: {html.escape(report["generated_at"])}</p>
  <p>Status: <span class="{status.lower()}">{status}</span></p>
  <table>
    <thead><tr><th>Check</th><th>Status</th><th>Duration ms</th><th>Summary</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</body>
</html>
"""


def main() -> int:
    report = generate_phase2_debug_report()
    print(json.dumps({"passed": report["passed"], "paths": report["paths"]}, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
