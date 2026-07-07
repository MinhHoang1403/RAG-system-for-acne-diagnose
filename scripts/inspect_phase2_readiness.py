#!/usr/bin/env python3
"""Read-only Phase 2 readiness inspection.

This script validates runtime compatibility with the hardened Phase 1 outputs.
It does not run ingestion, build indexes, call LLM/embedding providers, or write
to Qdrant/Neo4j/PostgreSQL/Redis.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env", override=False)
except ImportError:
    pass

from scripts.validate_kb_collections import inspect_qdrant_schema  # noqa: E402
from src.database.vector_store import qdrant_client_kwargs  # noqa: E402
from src.knowledge.entity_index import (  # noqa: E402
    get_chunk_collection_name,
    get_entity_collection_name,
)
from src.knowledge.versioning import get_embedding_metadata  # noqa: E402

logging.getLogger("httpx").setLevel(logging.WARNING)

EXPECTED_NEO4J_LABELS = {
    "ActiveIngredient": 7,
    "Condition": 1,
    "DrugClass": 6,
    "DrugProduct": 3,
    "SafetyContext": 4,
}
EXPECTED_NEO4J_RELATIONSHIPS = {
    "BELONGS_TO_CLASS": 11,
    "HAS_ACTIVE_INGREDIENT": 4,
}


def _check(
    name: str,
    passed: bool,
    details: dict[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "name": name,
        "passed": bool(passed),
        "details": details or {},
    }
    if error:
        record["error"] = error
    return record


async def inspect_qdrant() -> dict[str, Any]:
    from qdrant_client import AsyncQdrantClient  # type: ignore[import]

    checks: list[dict[str, Any]] = []
    chunk_collection = get_chunk_collection_name()
    entity_collection = get_entity_collection_name()
    expected_dimensions = int(get_embedding_metadata()["embedding_dimensions"])
    client = AsyncQdrantClient(**qdrant_client_kwargs())

    try:
        collections = await client.get_collections()
        existing = {collection.name for collection in collections.collections}
        checks.append(_check("qdrant_reachable", True, {"collections": sorted(existing)}))

        for role, collection_name, expected_points in (
            ("chunk", chunk_collection, None),
            ("entity", entity_collection, 20),
        ):
            if collection_name not in existing:
                checks.append(
                    _check(
                        f"qdrant_{role}_collection_exists",
                        False,
                        {"collection": collection_name},
                        f"{role} collection {collection_name!r} missing",
                    )
                )
                continue

            info = await client.get_collection(collection_name=collection_name)
            schema = inspect_qdrant_schema(info.config.params)
            points_count = int(getattr(info, "points_count", 0) or 0)
            details = {
                "collection": collection_name,
                "points_count": points_count,
                **schema,
            }
            schema_ok = (
                schema["has_dense"]
                and schema["dense_vector_name"] == "dense"
                and schema["dense_size"] == expected_dimensions
                and schema["has_bm25"]
                and schema["sparse_vector_name"] == "bm25"
            )
            points_ok = points_count > 0 if expected_points is None else points_count == expected_points
            checks.append(
                _check(
                    f"qdrant_{role}_schema_and_points",
                    schema_ok and points_ok,
                    details,
                    f"{role} collection schema/points mismatch" if not (schema_ok and points_ok) else None,
                )
            )
    except Exception as exc:
        checks.append(_check("qdrant_reachable", False, error=str(exc)))
    finally:
        await client.close()

    return {"checks": checks}


async def inspect_neo4j() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    try:
        from neo4j import AsyncGraphDatabase  # type: ignore[import]
    except ImportError as exc:
        return {"checks": [_check("neo4j_import", False, error=str(exc))]}

    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    driver = AsyncGraphDatabase.driver(
        uri,
        auth=(
            os.getenv("NEO4J_USERNAME", "neo4j"),
            os.getenv("NEO4J_PASSWORD", "password"),
        ),
    )
    try:
        async with driver.session() as session:
            label_counts: dict[str, int] = {}
            for label in EXPECTED_NEO4J_LABELS:
                result = await session.run(f"MATCH (n:{label}) RETURN count(n) AS count")
                record = await result.single()
                label_counts[label] = int(record["count"]) if record else 0

            rel_counts: dict[str, int] = {}
            for rel_type in EXPECTED_NEO4J_RELATIONSHIPS:
                result = await session.run(f"MATCH ()-[r:{rel_type}]->() RETURN count(r) AS count")
                record = await result.single()
                rel_counts[rel_type] = int(record["count"]) if record else 0

        node_total = sum(label_counts.values())
        rel_total = sum(rel_counts.values())
        details = {
            "uri": uri,
            "nodes": node_total,
            "relationships": rel_total,
            "labels": label_counts,
            "relationship_types": rel_counts,
        }
        passed = (
            node_total == 21
            and rel_total == 15
            and label_counts == EXPECTED_NEO4J_LABELS
            and rel_counts == EXPECTED_NEO4J_RELATIONSHIPS
        )
        checks.append(
            _check(
                "neo4j_deterministic_graph",
                passed,
                details,
                "Neo4j deterministic graph counts differ from Phase 1 baseline" if not passed else None,
            )
        )
    except Exception as exc:
        checks.append(_check("neo4j_reachable", False, {"uri": uri}, str(exc)))
    finally:
        await driver.close()

    return {"checks": checks}


def inspect_runtime_code() -> dict[str, Any]:
    retriever_source = (PROJECT_ROOT / "src" / "database" / "retriever.py").read_text(encoding="utf-8")
    graph_store_source = (PROJECT_ROOT / "src" / "database" / "graph_store.py").read_text(encoding="utf-8")

    return {
        "current_capabilities": {
            "qdrant_dense_search": "dense_results = await self._vector_store.search(" in retriever_source,
            "qdrant_sparse_bm25_search": "search_sparse" in retriever_source,
            "rrf_fusion": "rrf_fusion" in retriever_source,
            "legacy_query_metadata_boost": "extract_dermatology_metadata" in retriever_source,
            "neo4j_graph_context": "Neo4jGraphStore" in retriever_source,
            "neo4j_canonical_name_compatible": "canonical_name" in graph_store_source,
            "entity_collection_runtime_retrieval": "acne_entities_v1" in retriever_source
            or "get_entity_collection_name" in retriever_source,
            "drug_entity_normalizer_runtime": "DrugEntityNormalizer" in retriever_source,
        },
        "deferred_phase2_features": [
            "Route retrieval through acne_entities_v1 entity cards before chunk expansion.",
            "Use DrugEntityNormalizer/query intent metadata at runtime, not only legacy metadata boost.",
            "Add entity-aware context selection over drug_product, active_ingredient, drug_class, route, and safety_context.",
            "Use deterministic Neo4j graph as structured expansion, not only graph_nodes/keyword fallback.",
        ],
    }


async def main() -> int:
    runtime_config = {
        "chunk_collection": get_chunk_collection_name(),
        "entity_collection": get_entity_collection_name(),
        "qdrant_url": os.getenv("QDRANT_URL", "http://localhost:6333"),
        "embedding": get_embedding_metadata(),
        "kb_version": os.getenv("KB_VERSION", "acne_kb_v1"),
        "prompt_version": os.getenv("PROMPT_VERSION", "medical_prompt_v2"),
        "cache_answer_version": os.getenv("CACHE_ANSWER_VERSION", "v4"),
    }

    qdrant, neo4j = await asyncio.gather(inspect_qdrant(), inspect_neo4j())
    checks = qdrant["checks"] + neo4j["checks"]
    runtime_code = inspect_runtime_code()

    report = {
        "passed": all(check["passed"] for check in checks),
        "runtime_config": runtime_config,
        "phase1_state_checks": checks,
        **runtime_code,
        "recommended_next_step": "Phase 2A: entity-aware retrieval upgrade using acne_entities_v1 and deterministic Neo4j expansion.",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
