#!/usr/bin/env python3
"""Offline/local-model semantic reranker evaluation.

Offline mode is deterministic and uses a fake semantic backend. It validates the
pipeline and metrics; it is not a live semantic quality claim.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.retrieval.contracts import RetrievedCandidate  # noqa: E402
from src.retrieval.query_expansion import expand_normalized_query  # noqa: E402
from src.retrieval.query_normalization import normalize_query  # noqa: E402
from src.retrieval.reranker import rerank_candidates, rerank_provider_from_env  # noqa: E402
from src.retrieval.reranking.metrics import ranking_metrics  # noqa: E402
from src.retrieval.reranking.providers import LocalSemanticReranker, SemanticRerankerConfig  # noqa: E402

DEFAULT_CASES_PATH = PROJECT_ROOT / "tests" / "golden" / "semantic_reranker_cases.json"


class FixtureSemanticBackend:
    name = "fixture_semantic_backend"

    def __init__(self, relevance_by_text: dict[str, int]) -> None:
        self.relevance_by_text = relevance_by_text

    def score_pairs(
        self,
        query: str,
        documents: list[str],
        *,
        batch_size: int,
        timeout_seconds: float | None = None,
    ) -> list[float]:
        del query, batch_size, timeout_seconds
        return [float(self.relevance_by_text.get(document, 0)) for document in documents]


class FailingSemanticBackend:
    name = "failing_semantic_backend"

    def score_pairs(
        self,
        query: str,
        documents: list[str],
        *,
        batch_size: int,
        timeout_seconds: float | None = None,
    ) -> list[float]:
        del query, documents, batch_size, timeout_seconds
        raise RuntimeError("semantic_inference_error")


def load_cases(path: Path = DEFAULT_CASES_PATH) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_offline_eval(path: Path = DEFAULT_CASES_PATH) -> dict[str, Any]:
    cases = load_cases(path)
    baseline_case_metrics: list[dict[str, Any]] = []
    hybrid_case_metrics: list[dict[str, Any]] = []
    failures: list[str] = []
    fallback_checks = _fallback_checks()

    for case in cases:
        normalized = normalize_query(str(case["query"]))
        expansion = expand_normalized_query(normalized)
        candidates = _candidates_from_case(case)
        relevance = {
            str(item["candidate_id"]): int(item.get("relevance", 0))
            for item in case.get("candidates", [])
        }
        expected_top_ids = [str(item) for item in case.get("expected_top_ids", [])]

        baseline, baseline_trace = rerank_candidates(
            normalized,
            candidates,
            expansion,
            top_n=8,
            provider="local_rules",
        )
        fake_backend = FixtureSemanticBackend(
            {str(item["text"]): int(item.get("relevance", 0)) for item in case.get("candidates", [])}
        )
        hybrid, hybrid_trace = rerank_candidates(
            normalized,
            candidates,
            expansion,
            top_n=8,
            provider="hybrid",
            semantic_reranker=LocalSemanticReranker(
                SemanticRerankerConfig(model_path="fixture", max_candidates=32),
                backend=fake_backend,
            ),
        )

        baseline_ids = [candidate.candidate_id for candidate in baseline]
        hybrid_ids = [candidate.candidate_id for candidate in hybrid]
        baseline_case_metrics.append(
            {
                "id": case["id"],
                "provider": baseline_trace.provider,
                "ranked_ids": baseline_ids,
                "metrics": ranking_metrics(baseline_ids, relevance, k=5),
            }
        )
        hybrid_case_metrics.append(
            {
                "id": case["id"],
                "provider": hybrid_trace.provider,
                "ranked_ids": hybrid_ids,
                "metrics": ranking_metrics(hybrid_ids, relevance, k=5),
            }
        )
        if expected_top_ids and (not hybrid_ids or hybrid_ids[0] not in expected_top_ids):
            failures.append(f"{case['id']}: hybrid top1 {hybrid_ids[:1]} not in {expected_top_ids}")

    if not fallback_checks["semantic_failure_falls_back_to_local_rules"]:
        failures.append("fallback: semantic failure did not fall back to local_rules")

    return {
        "passed": not failures,
        "mode": "offline",
        "runtime_default_provider": rerank_provider_from_env(),
        "semantic_backend_available": False,
        "pipeline_checks": {
            "provider_contract": True,
            "local_rules_fallback": fallback_checks["semantic_failure_falls_back_to_local_rules"],
            "fixture_only": True,
            "not_a_live_quality_claim": True,
        },
        "baseline_metrics": _aggregate_metrics(baseline_case_metrics),
        "semantic_fixture_metrics": _aggregate_metrics(hybrid_case_metrics),
        "hybrid_fixture_metrics": _aggregate_metrics(hybrid_case_metrics),
        "fallback_checks": fallback_checks,
        "cases": {
            "baseline": baseline_case_metrics,
            "hybrid": hybrid_case_metrics,
        },
        "failures": failures,
    }


def run_local_model_audit(path: Path = DEFAULT_CASES_PATH) -> dict[str, Any]:
    del path
    config = SemanticRerankerConfig(
        model_path=_env("SEMANTIC_RERANK_MODEL_PATH"),
        device=_env("SEMANTIC_RERANK_DEVICE", "cpu"),
    )
    model_path = Path(config.model_path) if config.model_path else None
    if model_path is None or not model_path.exists():
        return {
            "passed": False,
            "mode": "local-model",
            "skipped": True,
            "reason": "local semantic model not provisioned",
            "model_downloaded": False,
            "external_api_used": False,
        }
    reranker = LocalSemanticReranker(config)
    return {
        "passed": reranker.available,
        "mode": "local-model",
        "skipped": False,
        "semantic_backend_available": reranker.available,
        "model_identifier": config.sanitized_model_identifier,
        "model_downloaded": False,
        "external_api_used": False,
    }


def _fallback_checks() -> dict[str, bool]:
    normalized = normalize_query("Benzoyl peroxide có phải kháng sinh không?")
    expansion = expand_normalized_query(normalized)
    candidates = [
        RetrievedCandidate(
            candidate_id="bp",
            source="chunk",
            collection="fixture",
            text="Benzoyl peroxide is not an antibiotic.",
            score=0.1,
            fused_score=0.1,
            payload={"chunk_id": "bp", "active_ingredient": ["benzoyl_peroxide"]},
            rank=1,
        )
    ]
    ranked, trace = rerank_candidates(
        normalized,
        candidates,
        expansion,
        provider="hybrid",
        semantic_reranker=LocalSemanticReranker(
            SemanticRerankerConfig(model_path="fixture", allow_fallback=True),
            backend=FailingSemanticBackend(),
        ),
    )
    return {
        "semantic_failure_falls_back_to_local_rules": bool(ranked)
        and trace.provider == "local_rules"
        and trace.fallback_used,
    }


def _candidates_from_case(case: dict[str, Any]) -> list[RetrievedCandidate]:
    output: list[RetrievedCandidate] = []
    for index, item in enumerate(case.get("candidates", []), start=1):
        candidate_id = str(item["candidate_id"])
        text = str(item.get("text") or "")
        output.append(
            RetrievedCandidate(
                candidate_id=candidate_id,
                source="chunk",
                collection="semantic_reranker_fixture",
                text=text,
                score=float(item.get("retrieval_score", 0.0)),
                fused_score=float(item.get("retrieval_score", 0.0)),
                payload={
                    "chunk_id": candidate_id,
                    "text": text,
                    "source_file": "semantic_reranker_cases.json",
                    "dense_score": item.get("dense_score"),
                    "sparse_score": item.get("sparse_score"),
                },
                rank=index,
            )
        )
    return output


def _aggregate_metrics(case_metrics: list[dict[str, Any]]) -> dict[str, float]:
    if not case_metrics:
        return {}
    metric_names = list(case_metrics[0]["metrics"].keys())
    return {
        name: round(sum(case["metrics"][name] for case in case_metrics) / len(case_metrics), 6)
        for name in metric_names
    }


def _env(name: str, default: str = "") -> str:
    import os

    return os.getenv(name, default).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Semantic reranker eval.")
    parser.add_argument("--mode", choices=["offline", "local-model"], default="offline")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    args = parser.parse_args()

    if args.mode == "local-model":
        report = run_local_model_audit(args.cases)
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return 0 if report.get("passed") else 2

    report = run_offline_eval(args.cases)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
