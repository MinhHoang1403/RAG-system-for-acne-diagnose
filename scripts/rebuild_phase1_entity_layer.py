#!/usr/bin/env python3
"""Controlled rebuild workflow for the Phase 1 entity layer.

This tool intentionally scopes writes to:

* Qdrant ``acne_entities_v1``
* the managed deterministic Neo4j entity graph

It never writes ``acne_knowledge`` and never edits the ingestion manifest.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
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

from src.database.vector_store import qdrant_client_kwargs  # noqa: E402
from src.integrations.google_genai import embed_texts_sync  # noqa: E402
from src.knowledge.entity_cards import build_entity_cards_from_taxonomy, entity_card_to_text  # noqa: E402
from src.knowledge.entity_index import (  # noqa: E402
    build_entity_point,
    build_entity_point_payload,
    ensure_entity_collection,
    entity_identity_key,
    get_chunk_collection_name,
    get_entity_collection_name,
    upsert_entity_cards,
)
from src.knowledge.graph_index import (  # noqa: E402
    apply_entity_graph_schema,
    get_neo4j_driver,
    sanitize_neo4j_properties,
    upsert_entity_graph,
    validate_entity_graph,
)
from src.knowledge.graph_schema import (  # noqa: E402
    CANONICAL_ENTITY_GRAPH_LABELS,
    CANONICAL_ENTITY_GRAPH_RELATIONSHIPS,
    build_entity_graph_records,
    summarize_graph_records,
)
from src.knowledge.schemas import EntityCard  # noqa: E402
from src.knowledge.versioning import get_embedding_metadata, get_knowledge_versions  # noqa: E402


TOOL_VERSION = "phase1_entity_layer_rebuild_v1"
REQUIRED_ENTITY_IDENTITIES = {
    "drug_product:tazorac",
    "active_ingredient:tazarotene",
    "drug_product:differin",
    "drug_product:epiduo",
}
REQUIRED_GRAPH_RELATIONS = {
    ("DrugProduct", "Tazorac", "HAS_ACTIVE_INGREDIENT", "ActiveIngredient", "tazarotene"),
    ("ActiveIngredient", "tazarotene", "BELONGS_TO_CLASS", "DrugClass", "topical_retinoid"),
    ("DrugProduct", "Differin", "HAS_ACTIVE_INGREDIENT", "ActiveIngredient", "adapalene"),
    ("DrugProduct", "Epiduo", "HAS_ACTIVE_INGREDIENT", "ActiveIngredient", "adapalene"),
    ("DrugProduct", "Epiduo", "HAS_ACTIVE_INGREDIENT", "ActiveIngredient", "benzoyl_peroxide"),
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Safely rebuild only the Phase 1 entity Qdrant collection and Neo4j entity graph.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Plan rebuild without writes.")
    mode.add_argument("--apply", action="store_true", help="Apply scoped entity-layer rebuild.")
    mode.add_argument("--verify", action="store_true", help="Verify current entity-layer state.")
    mode.add_argument("--rollback", action="store_true", help="Restore entity layer from backup.")
    parser.add_argument(
        "--backup-dir",
        help="Directory outside the repository for backup input/output.",
    )
    parser.add_argument(
        "--confirm-entity-layer-only",
        action="store_true",
        help="Required with --apply to confirm acne_knowledge and manifest are out of scope.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit compact JSON only.",
    )
    return parser.parse_args(argv)


def manifest_path() -> Path:
    return PROJECT_ROOT / "data" / "ingestion_manifest.json"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def desired_cards() -> list[EntityCard]:
    return build_entity_cards_from_taxonomy()


def desired_payloads(cards: list[EntityCard] | None = None) -> list[dict[str, Any]]:
    versions = get_knowledge_versions()
    return [
        build_entity_point_payload(card, kb_version=versions["kb_version"])
        for card in (cards or desired_cards())
    ]


def identity_set_from_payloads(payloads: list[dict[str, Any]]) -> set[str]:
    return {entity_identity_key(payload) for payload in payloads}


def relationship_set(records: dict[str, list[dict[str, Any]]]) -> set[tuple[str, str, str, str, str]]:
    return {
        (
            rel["source_label"],
            rel["source_name"],
            rel["relationship"],
            rel["target_label"],
            rel["target_name"],
        )
        for rel in records.get("relationships", [])
    }


def graph_node_set(records: dict[str, list[dict[str, Any]]]) -> set[tuple[str, str]]:
    return {
        (node["label"], node["canonical_name"])
        for node in records.get("nodes", [])
    }


def compare_sets(current: set[Any], proposed: set[Any]) -> dict[str, list[Any]]:
    return {
        "added": sorted(proposed - current),
        "removed": sorted(current - proposed),
        "unchanged": sorted(current & proposed),
    }


def summarize_rebuild_plan(
    *,
    current_entity_identities: set[str],
    current_graph_nodes: set[tuple[str, str]],
    current_graph_relationships: set[tuple[str, str, str, str, str]],
    knowledge_count: int,
    manifest_hash: str,
) -> dict[str, Any]:
    cards = desired_cards()
    payloads = desired_payloads(cards)
    desired_entity_identities = identity_set_from_payloads(payloads)
    desired_graph = build_entity_graph_records(cards)
    desired_nodes = graph_node_set(desired_graph)
    desired_relationships = relationship_set(desired_graph)
    entity_diff = compare_sets(current_entity_identities, desired_entity_identities)
    node_diff = compare_sets(current_graph_nodes, desired_nodes)
    relation_diff = compare_sets(current_graph_relationships, desired_relationships)
    summary = summarize_graph_records(desired_graph)
    return {
        "tool_version": TOOL_VERSION,
        "timestamp": now_iso(),
        "qdrant_entity_count_before": len(current_entity_identities),
        "qdrant_entity_count_proposed": len(desired_entity_identities),
        "entities_added": entity_diff["added"],
        "entities_changed": [],
        "entities_removed": entity_diff["removed"],
        "canonical_ids": sorted(desired_entity_identities),
        "neo4j_nodes_before": len(current_graph_nodes),
        "neo4j_nodes_proposed": len(desired_nodes),
        "neo4j_relationships_before": len(current_graph_relationships),
        "neo4j_relationships_proposed": len(desired_relationships),
        "graph_nodes_added": node_diff["added"],
        "graph_nodes_removed": node_diff["removed"],
        "relations_added": relation_diff["added"],
        "relations_removed": relation_diff["removed"],
        "desired_graph_summary": summary,
        "acne_knowledge_count": knowledge_count,
        "acne_knowledge_mutation_count": 0,
        "manifest_hash": manifest_hash,
        "manifest_mutation_count": 0,
        "required_entities_present": sorted(REQUIRED_ENTITY_IDENTITIES & desired_entity_identities),
        "missing_required_entities": sorted(REQUIRED_ENTITY_IDENTITIES - desired_entity_identities),
        "required_relations_present": sorted(REQUIRED_GRAPH_RELATIONS & desired_relationships),
        "missing_required_relations": sorted(REQUIRED_GRAPH_RELATIONS - desired_relationships),
    }


def validate_plan(plan: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if plan["acne_knowledge_mutation_count"] != 0:
        failures.append("acne_knowledge mutation count is not zero")
    if plan["manifest_mutation_count"] != 0:
        failures.append("manifest mutation count is not zero")
    if plan["entities_removed"]:
        failures.append(f"unexpected entity removals: {plan['entities_removed']}")
    if plan["relations_removed"]:
        failures.append(f"unexpected relation removals: {plan['relations_removed']}")
    if plan["missing_required_entities"]:
        failures.append(f"missing required entities: {plan['missing_required_entities']}")
    if plan["missing_required_relations"]:
        failures.append(f"missing required relations: {plan['missing_required_relations']}")
    duplicate_ids = [
        item for item, count in Counter(plan["canonical_ids"]).items()
        if count > 1
    ]
    if duplicate_ids:
        failures.append(f"duplicate canonical IDs: {duplicate_ids}")
    return failures


async def collect_runtime_snapshot() -> dict[str, Any]:
    from qdrant_client import AsyncQdrantClient  # type: ignore[import]

    entity_collection = get_entity_collection_name()
    chunk_collection = get_chunk_collection_name()
    client = AsyncQdrantClient(**qdrant_client_kwargs())
    try:
        entity_info = await client.get_collection(collection_name=entity_collection)
        knowledge_info = await client.get_collection(collection_name=chunk_collection)
        entity_points = await scroll_qdrant_points(
            client,
            collection_name=entity_collection,
            with_vectors=True,
        )
    finally:
        await client.close()
    driver = get_neo4j_driver()
    try:
        neo4j_graph = await export_neo4j_entity_graph(driver)
    finally:
        await driver.close()
    return {
        "entity_collection": entity_collection,
        "chunk_collection": chunk_collection,
        "entity_info": to_jsonable(entity_info),
        "knowledge_info": to_jsonable(knowledge_info),
        "entity_points": entity_points,
        "neo4j_graph": neo4j_graph,
        "manifest_path": str(manifest_path()),
        "manifest_hash": file_sha256(manifest_path()),
    }


async def scroll_qdrant_points(
    client: Any,
    *,
    collection_name: str,
    with_vectors: bool,
) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    offset: Any = None
    while True:
        batch, offset = await client.scroll(
            collection_name=collection_name,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=with_vectors,
        )
        for point in batch:
            points.append(
                {
                    "id": str(point.id),
                    "payload": to_jsonable(point.payload or {}),
                    "vector": to_jsonable(getattr(point, "vector", None)),
                }
            )
        if offset is None:
            break
    return points


async def export_neo4j_entity_graph(driver: Any) -> dict[str, Any]:
    labels = list(CANONICAL_ENTITY_GRAPH_LABELS)
    relationships = list(CANONICAL_ENTITY_GRAPH_RELATIONSHIPS)
    async with driver.session() as session:
        nodes: list[dict[str, Any]] = []
        for label in labels:
            result = await session.run(
                f"MATCH (n:{label}) RETURN labels(n) AS labels, properties(n) AS properties "
                "ORDER BY n.canonical_name"
            )
            async for record in result:
                nodes.append(
                    {
                        "label": label,
                        "labels": list(record["labels"]),
                        "properties": to_jsonable(record["properties"]),
                    }
                )

        rels: list[dict[str, Any]] = []
        for relationship in relationships:
            result = await session.run(
                f"MATCH (src)-[r:{relationship}]->(tgt) "
                "WHERE any(label IN labels(src) WHERE label IN $labels) "
                "AND any(label IN labels(tgt) WHERE label IN $labels) "
                "RETURN labels(src) AS source_labels, src.canonical_name AS source_name, "
                "type(r) AS relationship, labels(tgt) AS target_labels, "
                "tgt.canonical_name AS target_name, properties(r) AS properties "
                "ORDER BY source_name, relationship, target_name",
                labels=labels,
            )
            async for record in result:
                rels.append(
                    {
                        "source_label": first_managed_label(record["source_labels"]),
                        "source_name": record["source_name"],
                        "relationship": record["relationship"],
                        "target_label": first_managed_label(record["target_labels"]),
                        "target_name": record["target_name"],
                        "properties": to_jsonable(record["properties"]),
                    }
                )
    return {"nodes": nodes, "relationships": rels}


def current_identity_set(points: list[dict[str, Any]]) -> set[str]:
    identities: set[str] = set()
    for point in points:
        payload = point.get("payload") or {}
        try:
            identities.add(entity_identity_key(payload))
        except ValueError:
            continue
    return identities


def current_graph_node_set(graph: dict[str, Any]) -> set[tuple[str, str]]:
    return {
        (node["label"], node["properties"].get("canonical_name"))
        for node in graph.get("nodes", [])
        if node.get("label") and node.get("properties", {}).get("canonical_name")
    }


def current_graph_relationship_set(graph: dict[str, Any]) -> set[tuple[str, str, str, str, str]]:
    return {
        (
            rel["source_label"],
            rel["source_name"],
            rel["relationship"],
            rel["target_label"],
            rel["target_name"],
        )
        for rel in graph.get("relationships", [])
    }


async def dry_run() -> dict[str, Any]:
    snapshot = await collect_runtime_snapshot()
    plan = summarize_rebuild_plan(
        current_entity_identities=current_identity_set(snapshot["entity_points"]),
        current_graph_nodes=current_graph_node_set(snapshot["neo4j_graph"]),
        current_graph_relationships=current_graph_relationship_set(snapshot["neo4j_graph"]),
        knowledge_count=int(snapshot["knowledge_info"].get("points_count") or 0),
        manifest_hash=snapshot["manifest_hash"],
    )
    failures = validate_plan(plan)
    plan["passed"] = not failures
    plan["failures"] = failures
    return plan


async def write_backup(backup_dir: Path) -> dict[str, Any]:
    backup_dir = ensure_backup_dir(backup_dir)
    snapshot = await collect_runtime_snapshot()
    write_json(backup_dir / "qdrant_acne_entities_collection_info.json", snapshot["entity_info"])
    write_json(backup_dir / "qdrant_acne_entities_points.json", snapshot["entity_points"])
    write_json(backup_dir / "qdrant_acne_knowledge_collection_info.json", snapshot["knowledge_info"])
    write_json(backup_dir / "neo4j_entity_graph.json", snapshot["neo4j_graph"])
    manifest = {
        "tool_version": TOOL_VERSION,
        "created_at": now_iso(),
        "project_root": str(PROJECT_ROOT),
        "entity_collection": snapshot["entity_collection"],
        "chunk_collection": snapshot["chunk_collection"],
        "manifest_path": snapshot["manifest_path"],
        "manifest_hash": snapshot["manifest_hash"],
        "entity_point_count": len(snapshot["entity_points"]),
        "neo4j_node_count": len(snapshot["neo4j_graph"]["nodes"]),
        "neo4j_relationship_count": len(snapshot["neo4j_graph"]["relationships"]),
        "knowledge_point_count": int(snapshot["knowledge_info"].get("points_count") or 0),
        "hashes": {
            "qdrant_points": sha256_json(snapshot["entity_points"]),
            "neo4j_graph": sha256_json(snapshot["neo4j_graph"]),
        },
    }
    write_json(backup_dir / "backup_manifest.json", manifest)
    plan = await dry_run()
    write_json(backup_dir / "rebuild_plan.json", plan)
    return {"passed": True, "backup_dir": str(backup_dir), **manifest}


async def apply_rebuild(backup_dir: Path) -> dict[str, Any]:
    if not (backup_dir / "backup_manifest.json").exists():
        raise RuntimeError("Backup manifest is missing. Run backup before --apply.")
    plan = await dry_run()
    failures = validate_plan(plan)
    if failures:
        raise RuntimeError("Dry-run blockers before apply: " + "; ".join(failures))

    before_manifest_hash = file_sha256(manifest_path())
    before_knowledge_count = plan["acne_knowledge_count"]
    cards = desired_cards()
    embeddings = embed_cards(cards)
    entity_collection = get_entity_collection_name()
    shadow_collection = f"{entity_collection}_rebuild_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

    from qdrant_client import AsyncQdrantClient  # type: ignore[import]

    client = AsyncQdrantClient(**qdrant_client_kwargs())
    try:
        await ensure_entity_collection(client, shadow_collection, recreate=True)
        await upsert_entity_cards(
            cards,
            embeddings=embeddings,
            client=client,
            collection_name=shadow_collection,
            kb_version=get_knowledge_versions()["kb_version"],
        )
        await verify_qdrant_collection(client, shadow_collection)

        collections = await client.get_collections()
        names = {collection.name for collection in collections.collections}
        if entity_collection in names:
            await client.delete_collection(collection_name=entity_collection)
        await ensure_entity_collection(client, entity_collection, recreate=False)
        await upsert_entity_cards(
            cards,
            embeddings=embeddings,
            client=client,
            collection_name=entity_collection,
            kb_version=get_knowledge_versions()["kb_version"],
        )
        await verify_qdrant_collection(client, entity_collection)
        await client.delete_collection(collection_name=shadow_collection)
    finally:
        await client.close()

    records = build_entity_graph_records(cards)
    driver = get_neo4j_driver()
    try:
        await apply_entity_graph_schema(driver)
        graph_counts = await upsert_entity_graph(driver, records)
        graph_validation = await validate_entity_graph(driver)
    finally:
        await driver.close()

    verification = await verify_current_state(
        backup_manifest_path=backup_dir / "backup_manifest.json",
        expected_manifest_hash=before_manifest_hash,
        expected_knowledge_count=before_knowledge_count,
    )
    if not verification["passed"]:
        raise RuntimeError("Post-apply verification failed: " + "; ".join(verification["failures"]))
    return {
        "passed": True,
        "shadow_collection": shadow_collection,
        "qdrant_entity_collection": entity_collection,
        "neo4j_upserted": graph_counts,
        "neo4j_validation": graph_validation,
        "verification": verification,
    }


async def verify_current_state(
    *,
    backup_manifest_path: Path | None = None,
    expected_manifest_hash: str | None = None,
    expected_knowledge_count: int | None = None,
) -> dict[str, Any]:
    backup_manifest = read_json(backup_manifest_path) if backup_manifest_path and backup_manifest_path.exists() else {}
    expected_manifest_hash = expected_manifest_hash or backup_manifest.get("manifest_hash")
    expected_knowledge_count = expected_knowledge_count or backup_manifest.get("knowledge_point_count")
    snapshot = await collect_runtime_snapshot()
    identities = current_identity_set(snapshot["entity_points"])
    graph_relationships = current_graph_relationship_set(snapshot["neo4j_graph"])
    current_manifest_hash = snapshot["manifest_hash"]
    knowledge_count = int(snapshot["knowledge_info"].get("points_count") or 0)
    failures: list[str] = []
    if expected_manifest_hash and current_manifest_hash != expected_manifest_hash:
        failures.append("manifest hash changed")
    if expected_knowledge_count is not None and knowledge_count != int(expected_knowledge_count):
        failures.append("acne_knowledge point count changed")
    missing_entities = sorted(REQUIRED_ENTITY_IDENTITIES - identities)
    if missing_entities:
        failures.append(f"missing required qdrant entities: {missing_entities}")
    missing_relations = sorted(REQUIRED_GRAPH_RELATIONS - graph_relationships)
    if missing_relations:
        failures.append(f"missing required graph relations: {missing_relations}")
    duplicate_identities = duplicate_entities(snapshot["entity_points"])
    if duplicate_identities:
        failures.append(f"duplicate qdrant entity identities: {duplicate_identities}")
    duplicate_relations = duplicate_graph_relationships(snapshot["neo4j_graph"])
    if duplicate_relations:
        failures.append(f"duplicate neo4j relations: {duplicate_relations}")
    return {
        "passed": not failures,
        "failures": failures,
        "entity_count": len(identities),
        "knowledge_count": knowledge_count,
        "manifest_hash": current_manifest_hash,
        "required_entities": sorted(REQUIRED_ENTITY_IDENTITIES),
        "required_relations": sorted(REQUIRED_GRAPH_RELATIONS),
        "acne_knowledge_mutation_count": 0,
        "manifest_mutation_count": 0,
    }


async def rollback(backup_dir: Path) -> dict[str, Any]:
    manifest = read_json(backup_dir / "backup_manifest.json")
    entity_points = read_json(backup_dir / "qdrant_acne_entities_points.json")
    neo4j_graph = read_json(backup_dir / "neo4j_entity_graph.json")
    entity_collection = manifest["entity_collection"]

    from qdrant_client import AsyncQdrantClient  # type: ignore[import]
    from qdrant_client.models import PointStruct  # type: ignore[import]

    client = AsyncQdrantClient(**qdrant_client_kwargs())
    try:
        collections = await client.get_collections()
        names = {collection.name for collection in collections.collections}
        if entity_collection in names:
            await client.delete_collection(collection_name=entity_collection)
        await ensure_entity_collection(client, entity_collection, recreate=False)
        points = [
            PointStruct(id=point["id"], vector=point["vector"], payload=point["payload"])
            for point in entity_points
        ]
        for start in range(0, len(points), 64):
            await client.upsert(
                collection_name=entity_collection,
                points=points[start:start + 64],
            )
    finally:
        await client.close()

    driver = get_neo4j_driver()
    try:
        await restore_neo4j_entity_graph(driver, neo4j_graph)
    finally:
        await driver.close()

    verification = await verify_rollback(backup_dir)
    return {"passed": verification["passed"], "rollback_verification": verification}


async def verify_rollback(backup_dir: Path) -> dict[str, Any]:
    manifest = read_json(backup_dir / "backup_manifest.json")
    snapshot = await collect_runtime_snapshot()
    failures: list[str] = []
    if len(snapshot["entity_points"]) != int(manifest["entity_point_count"]):
        failures.append("entity point count does not match backup")
    if len(snapshot["neo4j_graph"]["nodes"]) != int(manifest["neo4j_node_count"]):
        failures.append("Neo4j node count does not match backup")
    if len(snapshot["neo4j_graph"]["relationships"]) != int(manifest["neo4j_relationship_count"]):
        failures.append("Neo4j relationship count does not match backup")
    if snapshot["manifest_hash"] != manifest["manifest_hash"]:
        failures.append("manifest hash changed during rollback")
    return {"passed": not failures, "failures": failures}


async def restore_neo4j_entity_graph(driver: Any, graph: dict[str, Any]) -> None:
    labels = list(CANONICAL_ENTITY_GRAPH_LABELS)
    relationships = list(CANONICAL_ENTITY_GRAPH_RELATIONSHIPS)
    async with driver.session() as session:
        for relationship in relationships:
            await session.run(
                f"MATCH (src)-[r:{relationship}]->(tgt) "
                "WHERE any(label IN labels(src) WHERE label IN $labels) "
                "AND any(label IN labels(tgt) WHERE label IN $labels) "
                "DELETE r",
                labels=labels,
            )
        for label in labels:
            await session.run(f"MATCH (n:{label}) DETACH DELETE n")
        for node in graph.get("nodes", []):
            label = first_managed_label(node.get("labels") or [node["label"]])
            properties = sanitize_neo4j_properties(node["properties"])
            await session.run(
                (
                    f"MERGE (n:{label} {{canonical_name: $canonical_name}}) "
                    "SET n += $properties"
                ),
                canonical_name=properties["canonical_name"],
                properties=properties,
            )
        for rel in graph.get("relationships", []):
            source_label = rel["source_label"]
            target_label = rel["target_label"]
            relationship = rel["relationship"]
            properties = sanitize_neo4j_properties(rel.get("properties") or {})
            await session.run(
                (
                    f"MATCH (src:{source_label} {{canonical_name: $source_name}}) "
                    f"MATCH (tgt:{target_label} {{canonical_name: $target_name}}) "
                    f"MERGE (src)-[r:{relationship}]->(tgt) "
                    "SET r += $properties"
                ),
                source_name=rel["source_name"],
                target_name=rel["target_name"],
                properties=properties,
            )


async def verify_qdrant_collection(client: Any, collection_name: str) -> None:
    points = await scroll_qdrant_points(client, collection_name=collection_name, with_vectors=False)
    identities = current_identity_set(points)
    missing = REQUIRED_ENTITY_IDENTITIES - identities
    if missing:
        raise RuntimeError(f"Qdrant collection {collection_name} missing entities: {sorted(missing)}")


def embed_cards(cards: list[EntityCard]) -> list[list[float]]:
    api_key = os.getenv("GOOGLE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY is required for --apply.")
    metadata = get_embedding_metadata()
    return embed_texts_sync(
        [entity_card_to_text(card) for card in cards],
        model_name=metadata["embedding_model"],
        task_type="retrieval_document",
        expected_dimensions=int(metadata["embedding_dimensions"]),
        api_key=api_key,
    )


def duplicate_entities(points: list[dict[str, Any]]) -> dict[str, list[str]]:
    seen: dict[str, str] = {}
    duplicates: dict[str, list[str]] = {}
    for point in points:
        try:
            identity = entity_identity_key(point.get("payload") or {})
        except ValueError:
            continue
        point_id = str(point["id"])
        if identity in seen and seen[identity] != point_id:
            duplicates.setdefault(identity, [seen[identity]]).append(point_id)
        else:
            seen[identity] = point_id
    return duplicates


def duplicate_graph_relationships(graph: dict[str, Any]) -> dict[str, int]:
    counts = Counter(
        (
            rel["source_label"],
            rel["source_name"],
            rel["relationship"],
            rel["target_label"],
            rel["target_name"],
        )
        for rel in graph.get("relationships", [])
    )
    return {str(key): count for key, count in counts.items() if count > 1}


def ensure_backup_dir(path: Path) -> Path:
    path = path.resolve()
    project = PROJECT_ROOT.resolve()
    if path == project or project in path.parents:
        raise RuntimeError("Backup directory must be outside the repository.")
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, data: Any) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )


def read_json(path: Path | None) -> Any:
    if path is None:
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_json(data: Any) -> str:
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def to_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if hasattr(value, "model_dump"):
        return to_jsonable(value.model_dump(mode="json"))
    if hasattr(value, "dict"):
        return to_jsonable(value.dict())
    return str(value)


def first_managed_label(labels: list[str]) -> str:
    for label in labels:
        if label in CANONICAL_ENTITY_GRAPH_LABELS:
            return label
    raise ValueError(f"No managed entity label found in {labels!r}")


def print_report(report: dict[str, Any], *, compact: bool = False) -> None:
    print(json.dumps(report, ensure_ascii=False, indent=None if compact else 2, sort_keys=True, default=str))


async def async_main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if get_entity_collection_name() == get_chunk_collection_name():
        raise RuntimeError("Entity collection and chunk collection must be different.")

    backup_dir = Path(args.backup_dir) if args.backup_dir else None
    if args.dry_run:
        report = await dry_run()
        print_report(report, compact=args.json)
        return 0 if report["passed"] else 1
    if args.verify:
        report = await verify_current_state(
            backup_manifest_path=(backup_dir / "backup_manifest.json") if backup_dir else None
        )
        print_report(report, compact=args.json)
        return 0 if report["passed"] else 1
    if args.rollback:
        if backup_dir is None:
            raise RuntimeError("--rollback requires --backup-dir.")
        report = await rollback(backup_dir)
        print_report(report, compact=args.json)
        return 0 if report["passed"] else 1
    if args.apply:
        if backup_dir is None:
            raise RuntimeError("--apply requires --backup-dir.")
        if not args.confirm_entity_layer_only:
            raise RuntimeError("--apply requires --confirm-entity-layer-only.")
        report = await apply_rebuild(backup_dir)
        print_report(report, compact=args.json)
        return 0 if report["passed"] else 1
    if backup_dir is None:
        raise RuntimeError("Backup mode requires --backup-dir.")
    report = await write_backup(backup_dir)
    print_report(report, compact=args.json)
    return 0


def main() -> int:
    return asyncio.run(async_main())


if __name__ == "__main__":
    raise SystemExit(main())
