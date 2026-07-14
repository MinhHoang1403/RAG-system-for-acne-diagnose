"""Audit 13 benchmark evaluator.

The default mode is read-only and offline-safe: it evaluates query
normalization, prompt/presentation contracts, source-label rules and benchmark
metadata. Use ``--live-retrieval`` to add Qdrant/Neo4j retrieval metrics.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env", override=False)
except Exception:
    pass

from src.agent.answer_formatting import ANSWER_FORMATTING_CONTRACT, answer_format_instruction_for_question  # noqa: E402
from src.agent.source_presentation import build_source_metadata  # noqa: E402
from src.database.retriever import HybridRetriever  # noqa: E402
from src.retrieval.query_normalization import normalize_query  # noqa: E402


FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "answer_quality_audit_v13.json"
TECHNICAL_SOURCE_PATTERNS = ["entity:", ".json", ".pdf", "Qd 4416 Cut", "Piis0190962223033893"]


def _key(text: str) -> str:
    value = text.casefold().replace("_", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _entity_present(entity: str, normalized: dict[str, Any]) -> bool:
    key = _key(entity)
    fields = [
        normalized.get("drug_product", []),
        normalized.get("active_ingredient", []),
        normalized.get("drug_class", []),
        normalized.get("condition", []),
        normalized.get("safety_context", []),
        normalized.get("aliases", []),
    ]
    joined = " ".join(_key(str(item)) for values in fields for item in values)
    if key in joined:
        return True
    if key == "retinoid":
        return "retinoid" in joined
    if key == "pregnancy":
        return "pregnancy" in joined or "thai" in joined or "mang thai" in joined
    return False


def _load_cases(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def _evaluate_normalization(case: dict[str, Any]) -> tuple[bool, list[str], dict[str, Any]]:
    normalized = normalize_query(case["query"]).model_dump(mode="json")
    failures: list[str] = []
    expected_intents = case.get("expected_intents") or []
    if expected_intents and normalized.get("intent") not in expected_intents:
        failures.append(f"intent={normalized.get('intent')} expected_one_of={expected_intents}")
    for entity in case.get("required_entities") or []:
        if entity == "pregnancy":
            if "pregnancy" not in " ".join(normalized.get("safety_context", [])).casefold() and "thai" not in normalized.get("normalized_text", ""):
                failures.append(f"missing_entity={entity}")
        elif not _entity_present(entity, normalized):
            failures.append(f"missing_entity={entity}")
    return not failures, failures, normalized


def _evaluate_prompt_contract(case: dict[str, Any]) -> tuple[bool, list[str]]:
    question = case["query"]
    instruction = answer_format_instruction_for_question(question)
    prompt_text = f"{ANSWER_FORMATTING_CONTRACT}\n{instruction}".casefold()
    failures = []
    if case.get("required_table_fields"):
        if "bảng" not in prompt_text and "table" not in prompt_text:
            failures.append("prompt_does_not_encourage_table")
        for field in case["required_table_fields"]:
            if field.casefold() not in question.casefold() and field.casefold() not in prompt_text:
                failures.append(f"missing_table_field_instruction={field}")
    if case.get("required_list_count"):
        count = str(case["required_list_count"])
        if count not in question and count not in prompt_text:
            failures.append("requested_count_not_visible")
    if case.get("category") == "comparison":
        if "cover đầy đủ" not in prompt_text and "mọi entity" not in prompt_text:
            failures.append("comparison_completeness_rule_missing")
    return not failures, failures


def _evaluate_source_presentation() -> tuple[bool, list[str], list[dict[str, Any]]]:
    metadata = build_source_metadata(
        ["entity:active_ingredient", "PIIS0190962223033893.pdf", "web_raw_dataset.json"],
        [
            {"source_file": "entity:active_ingredient", "retrieval_source": "entity", "entity_type": "active_ingredient"},
            {"source_file": "PIIS0190962223033893.pdf", "source_path": "C:/x/PIIS0190962223033893.pdf"},
            {"source_file": "web_raw_dataset.json", "source_path": "C:/x/web_raw_dataset.json"},
        ],
    )
    labels = [item.get("display_name", "") for item in metadata]
    failures = []
    for label in labels:
        for pattern in TECHNICAL_SOURCE_PATTERNS:
            if pattern.casefold() in label.casefold():
                failures.append(f"raw_source_label_visible={label}")
    return not failures, failures, metadata


async def _live_retrieval_metrics(cases: list[dict[str, Any]]) -> dict[str, Any]:
    retriever = HybridRetriever()
    total = 0
    recall5 = 0
    recall10 = 0
    mrr_sum = 0.0
    entity_coverage = 0
    details = []
    try:
        for case in cases:
            required = case.get("required_entities") or []
            if not required:
                continue
            total += 1
            result = await retriever.retrieve(case["query"], top_k=5)
            trace = result.metadata.get("retrieval_trace") or {}
            candidates = trace.get("merged_candidates") or []
            haystack = []
            for candidate in candidates:
                payload = candidate.get("payload") or {}
                haystack.append(" ".join(str(payload.get(key, "")) for key in ["canonical_name", "entity_type", "text", "source_file"]))
            ranks = []
            for entity in required:
                entity_key = _key(entity)
                rank = None
                for idx, text in enumerate(haystack, 1):
                    if entity_key in _key(text):
                        rank = idx
                        break
                if rank is not None:
                    ranks.append(rank)
            covered = len(ranks) == len(required)
            if covered:
                entity_coverage += 1
            if any(rank <= 5 for rank in ranks):
                recall5 += 1
            if any(rank <= 10 for rank in ranks):
                recall10 += 1
            if ranks:
                mrr_sum += 1.0 / min(ranks)
            details.append(
                {
                    "id": case["id"],
                    "required_entities": required,
                    "covered_all_required": covered,
                    "best_rank": min(ranks) if ranks else None,
                    "candidate_count": len(candidates),
                }
            )
    finally:
        await retriever.close()
    denom = max(total, 1)
    return {
        "evaluated_cases": total,
        "recall_at_5": round(recall5 / denom, 4),
        "recall_at_10": round(recall10 / denom, 4),
        "mrr": round(mrr_sum / denom, 4),
        "entity_coverage": round(entity_coverage / denom, 4),
        "details": details,
    }


async def run(args: argparse.Namespace) -> dict[str, Any]:
    cases = _load_cases(Path(args.fixture))
    case_results = []
    passed_cases = 0
    critical_failures = 0
    category_scores: dict[str, dict[str, int]] = {}

    for case in cases:
        norm_passed, norm_failures, normalized = _evaluate_normalization(case)
        prompt_passed, prompt_failures = _evaluate_prompt_contract(case)
        failures = norm_failures + prompt_failures
        passed = not failures
        passed_cases += int(passed)
        critical_failures += int(bool(failures) and bool(case.get("critical_safety")))
        bucket = category_scores.setdefault(case.get("category", "unknown"), {"total": 0, "passed": 0})
        bucket["total"] += 1
        bucket["passed"] += int(passed)
        case_results.append(
            {
                "id": case["id"],
                "category": case.get("category"),
                "passed": passed,
                "failures": failures,
                "intent": normalized.get("intent"),
                "entities": {
                    "drug_product": normalized.get("drug_product", []),
                    "active_ingredient": normalized.get("active_ingredient", []),
                    "drug_class": normalized.get("drug_class", []),
                    "condition": normalized.get("condition", []),
                    "safety_context": normalized.get("safety_context", []),
                },
            }
        )

    source_passed, source_failures, source_metadata = _evaluate_source_presentation()
    if not source_passed:
        critical_failures += 1

    retrieval_metrics = None
    if args.live_retrieval:
        retrieval_metrics = await _live_retrieval_metrics(cases)

    total = len(cases)
    passed = passed_cases == total and source_passed and critical_failures == 0
    return {
        "passed": passed,
        "total": total,
        "passed_cases": passed_cases,
        "failed_cases": total - passed_cases,
        "critical_failures": critical_failures,
        "category_scores": category_scores,
        "source_presentation": {
            "passed": source_passed,
            "failures": source_failures,
            "metadata": source_metadata,
        },
        "retrieval_metrics": retrieval_metrics,
        "cases": case_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate Audit 13 semantic constraints.")
    parser.add_argument("--fixture", default=str(FIXTURE))
    parser.add_argument("--live-retrieval", action="store_true")
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    report = asyncio.run(run(args))
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
