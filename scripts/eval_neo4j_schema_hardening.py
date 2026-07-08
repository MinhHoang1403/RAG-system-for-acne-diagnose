#!/usr/bin/env python3
"""Offline/integration evaluation for Neo4j schema hardening."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.validate_neo4j_schema import collect_neo4j_snapshot, offline_snapshot, validate_snapshot  # noqa: E402
from src.database.neo4j_queries import (  # noqa: E402
    ENTITY_CONTEXT_CYPHER,
    KEYWORD_SEARCH_CYPHER,
    extract_neo4j_notifications,
    is_critical_neo4j_notification,
)
from src.knowledge.graph_schema import LEGACY_GRAPH_PROPERTIES  # noqa: E402


def _check(name: str, passed: bool, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "details": details or {}}


class _FakeNotification:
    gql_status = "01N52"
    status_description = "warn: property key does not exist. The property `name` does not exist."
    raw_severity = "WARNING"
    raw_classification = "UNRECOGNIZED"


class _FakeSummary:
    gql_status_objects = [_FakeNotification()]


def _offline_checks() -> list[dict[str, Any]]:
    queries = f"{ENTITY_CONTEXT_CYPHER}\n{KEYWORD_SEARCH_CYPHER}"
    legacy_static_access = [
        prop
        for prop in LEGACY_GRAPH_PROPERTIES
        if f".{prop}" in queries
    ]
    notifications = extract_neo4j_notifications(_FakeSummary())
    schema_report = validate_snapshot(offline_snapshot())
    return [
        _check("canonical_schema_contract", schema_report["passed"], {"failures": schema_report["failures"]}),
        _check("legacy_static_property_access_removed", not legacy_static_access, {"legacy_static_access": legacy_static_access}),
        _check(
            "notification_classifier_detects_missing_property",
            bool(notifications) and is_critical_neo4j_notification(notifications[0]),
            {"notifications": notifications},
        ),
        _check("query_projection_compatible", " AS entity" in queries and " AS evidence" in queries),
        _check("query_limits_present", "$limit" in ENTITY_CONTEXT_CYPHER and "$limit" in KEYWORD_SEARCH_CYPHER),
    ]


async def run_eval(mode: str) -> dict[str, Any]:
    if mode == "offline":
        checks = _offline_checks()
    else:
        schema_report = validate_snapshot(await collect_neo4j_snapshot())
        checks = [
            _check("integration_schema_validation", schema_report["passed"], {"failures": schema_report["failures"]}),
            _check("integration_node_count_read", schema_report["node_count"] > 0, {"node_count": schema_report["node_count"]}),
            _check(
                "integration_relationship_count_read",
                schema_report["relationship_count"] > 0,
                {"relationship_count": schema_report["relationship_count"]},
            ),
            _check(
                "integration_runtime_query_notifications_clean",
                next(
                    (
                        item
                        for item in schema_report["checks"]
                        if item["name"] == "runtime_queries_without_critical_notifications"
                    ),
                    {"passed": False, "details": {}},
                )["passed"],
            ),
        ]

    failed = [check for check in checks if not check["passed"]]
    return {
        "passed": not failed,
        "mode": mode,
        "total_checks": len(checks),
        "passed_checks": len(checks) - len(failed),
        "failed_checks": len(failed),
        "checks": checks,
        "failures": failed,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate Neo4j schema hardening.")
    parser.add_argument("--mode", choices=["offline", "integration"], default="offline")
    return parser.parse_args(argv)


async def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = await run_eval(args.mode)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
