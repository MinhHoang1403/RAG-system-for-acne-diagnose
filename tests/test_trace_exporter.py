from __future__ import annotations

import json

from src.observability.trace_exporter import (
    build_observability_event,
    export_observability_event,
)


def test_exporter_disabled_does_not_write(tmp_path):
    event = build_observability_event(query="Mụn đầu đen là gì?")

    exported = export_observability_event(event, output_dir=tmp_path, enabled=False)

    assert exported is False
    assert list(tmp_path.iterdir()) == []


def test_exporter_writes_jsonl_when_enabled(tmp_path):
    event = build_observability_event(
        query="Benzoyl peroxide có phải kháng sinh không?",
        result={
            "answer_quality_report": {"passed": True, "issues": []},
            "cache_hit": False,
        },
        safe_payload={"api_key": "secret", "context_text": "x" * 20},
        max_text_chars=8,
    )

    exported = export_observability_event(event, output_dir=tmp_path, enabled=True)

    files = list(tmp_path.glob("phase2_traces-*.jsonl"))
    assert exported is True
    assert len(files) == 1
    payload = json.loads(files[0].read_text(encoding="utf-8").splitlines()[0])
    assert payload["safe_payload"]["api_key"] == "[REDACTED]"
    assert "truncated" in payload["safe_payload"]["context_text"]
    assert payload["summary"]["pipeline_fingerprint"]
