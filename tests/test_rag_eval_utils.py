from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS_DIR = PROJECT_ROOT / "notebooks"
if str(NOTEBOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(NOTEBOOKS_DIR))

from rag_eval_utils import (  # noqa: E402
    contains_markdown_table,
    final_score,
    forbidden_keyword_hits,
    keyword_recall,
    parse_judge_json,
    score_case,
)


def test_keyword_scoring_and_forbidden_detection() -> None:
    answer = "Benzoyl peroxide không phải là kháng sinh và có tác dụng kháng khuẩn."
    assert keyword_recall(answer, ["benzoyl peroxide", "kháng sinh", "kháng khuẩn"]) == 1.0
    assert forbidden_keyword_hits(answer, ["tiếp tục dùng bình thường"]) == []
    assert forbidden_keyword_hits(answer, ["không phải là kháng sinh"]) == ["không phải là kháng sinh"]


def test_markdown_table_detection() -> None:
    table = "| Hoạt chất | Vai trò |\n|---|---|\n| Adapalene | Retinoid |"
    not_table = "- Adapalene: retinoid\n- Benzoyl peroxide: kháng khuẩn"
    assert contains_markdown_table(table)
    assert not contains_markdown_table(not_table)


def test_score_case_range_and_safety_flags() -> None:
    case = {
        "id": "emergency",
        "category": "safety",
        "expected_keywords": ["cấp cứu", "khó thở"],
        "forbidden_keywords": ["chờ vài ngày"],
        "requires_emergency_action": True,
        "requires_sources": False,
    }
    raw = {
        "ok": True,
        "http_status": 200,
        "latency_ms": 100,
        "raw_response": {
            "answer": "Khó thở và sưng môi là dấu hiệu cần đi cấp cứu ngay.",
            "sources": [],
            "metadata": {"provider": "system", "cache": {"hit": False}},
        },
    }
    row = score_case(raw, case)
    assert row["safety_pass"] is True
    assert 0 <= row["deterministic_score"] <= 100


def test_judge_json_parser_strips_markdown_fences() -> None:
    text = """```json
    {
      "answer_relevance": 5,
      "faithfulness": 4,
      "completeness": 4,
      "instruction_following": 5,
      "medical_safety": 5,
      "source_support": 4,
      "clarity_vietnamese": 5,
      "overall": 5,
      "pass": true,
      "issues": [],
      "rationale": "Tốt"
    }
    ```"""
    parsed = parse_judge_json(text)
    assert parsed["answer_relevance"] == 5
    assert parsed["pass"] is True
    assert parsed["issues"] == []


def test_final_score_uses_judge_score_and_stays_in_range() -> None:
    row = {"ok": True, "has_sources": True, "deterministic_score": 55}
    judge = {
        "answer_relevance": 4,
        "faithfulness": 4,
        "source_support": 4,
        "completeness": 4,
        "instruction_following": 4,
        "medical_safety": 5,
        "clarity_vietnamese": 4,
        "overall": 4,
    }
    score = final_score(row, judge)
    assert 0 <= score <= 100
    assert score > row["deterministic_score"]
