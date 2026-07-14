"""Neo4j upsert helpers for deterministic taxonomy/entity graph records."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from src.knowledge.graph_schema import (
    ENTITY_GRAPH_LABELS,
    ENTITY_GRAPH_RELATIONSHIPS,
    get_entity_graph_constraints,
    get_entity_graph_indexes,
)


logger = logging.getLogger(__name__)

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

PrimitiveNeo4jValue = str | int | float | bool


def get_neo4j_driver() -> Any:
    """Create an async Neo4j driver using the project's env config."""

    try:
        from neo4j import AsyncGraphDatabase  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError("Missing dependency. Run: pip install neo4j") from exc

    return AsyncGraphDatabase.driver(
        NEO4J_URI,
        auth=(NEO4J_USERNAME, NEO4J_PASSWORD),
    )


async def apply_entity_graph_schema(driver: Any) -> None:
    """Apply deterministic entity graph constraints and indexes."""

    async with driver.session() as session:
        for statement in get_entity_graph_constraints():
            await session.run(statement)
        for statement in get_entity_graph_indexes():
            await session.run(statement)


async def upsert_entity_graph(driver: Any, records: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    """MERGE deterministic entity graph nodes and relationships into Neo4j."""

    node_count = 0
    relationship_count = 0

    async with driver.session() as session:
        for node in records.get("nodes", []):
            label = _safe_label(node["label"])
            properties = sanitize_neo4j_properties(
                {key: value for key, value in node.items() if key != "label"}
            )
            await session.run(
                (
                    f"MERGE (n:{label} {{canonical_name: $canonical_name}}) "
                    "ON CREATE SET n.created_at = datetime() "
                    "SET n += $properties, "
                    "n.updated_at = datetime()"
                ),
                canonical_name=node["canonical_name"],
                properties=properties,
            )
            node_count += 1

        for relationship in records.get("relationships", []):
            source_label = _safe_label(relationship["source_label"])
            target_label = _safe_label(relationship["target_label"])
            rel_type = _safe_relationship(relationship["relationship"])
            properties = sanitize_neo4j_properties(
                dict(relationship.get("properties") or {})
            )
            await session.run(
                (
                    f"MATCH (src:{source_label} {{canonical_name: $source_name}}) "
                    f"MATCH (tgt:{target_label} {{canonical_name: $target_name}}) "
                    f"MERGE (src)-[r:{rel_type}]->(tgt) "
                    "ON CREATE SET r.created_at = datetime() "
                    "SET r += $properties, "
                    "r.updated_at = datetime()"
                ),
                source_name=relationship["source_name"],
                target_name=relationship["target_name"],
                properties=properties,
            )
            relationship_count += 1

    logger.info(
        "Entity graph upsert complete: nodes=%d relationships=%d",
        node_count,
        relationship_count,
    )
    return {"nodes": node_count, "relationships": relationship_count}


async def validate_entity_graph(driver: Any) -> dict[str, Any]:
    """Validate minimal deterministic relationships in Neo4j."""

    required_checks = {
        "dalacin_has_clindamycin": (
            "MATCH (:DrugProduct {canonical_name:'Dalacin T'})"
            "-[:HAS_ACTIVE_INGREDIENT]->"
            "(:ActiveIngredient {canonical_name:'clindamycin'}) RETURN count(*) AS count"
        ),
        "clindamycin_topical_antibiotic": (
            "MATCH (:ActiveIngredient {canonical_name:'clindamycin'})"
            "-[:BELONGS_TO_CLASS]->"
            "(:DrugClass {canonical_name:'topical_antibiotic'}) RETURN count(*) AS count"
        ),
        "epiduo_has_adapalene": (
            "MATCH (:DrugProduct {canonical_name:'Epiduo'})"
            "-[:HAS_ACTIVE_INGREDIENT]->"
            "(:ActiveIngredient {canonical_name:'adapalene'}) RETURN count(*) AS count"
        ),
        "epiduo_has_bpo": (
            "MATCH (:DrugProduct {canonical_name:'Epiduo'})"
            "-[:HAS_ACTIVE_INGREDIENT]->"
            "(:ActiveIngredient {canonical_name:'benzoyl_peroxide'}) RETURN count(*) AS count"
        ),
        "differin_has_adapalene": (
            "MATCH (:DrugProduct {canonical_name:'Differin'})"
            "-[:HAS_ACTIVE_INGREDIENT]->"
            "(:ActiveIngredient {canonical_name:'adapalene'}) RETURN count(*) AS count"
        ),
        "tazorac_has_tazarotene": (
            "MATCH (:DrugProduct {canonical_name:'Tazorac'})"
            "-[:HAS_ACTIVE_INGREDIENT]->"
            "(:ActiveIngredient {canonical_name:'tazarotene'}) RETURN count(*) AS count"
        ),
        "tazarotene_topical_retinoid": (
            "MATCH (:ActiveIngredient {canonical_name:'tazarotene'})"
            "-[:BELONGS_TO_CLASS]->"
            "(:DrugClass {canonical_name:'topical_retinoid'}) RETURN count(*) AS count"
        ),
        "bpo_not_topical_or_oral_antibiotic": (
            "MATCH (:ActiveIngredient {canonical_name:'benzoyl_peroxide'})"
            "-[:BELONGS_TO_CLASS]->"
            "(c:DrugClass) "
            "WHERE c.canonical_name IN ['topical_antibiotic', 'oral_antibiotic'] "
            "RETURN count(*) AS count"
        ),
    }

    results: dict[str, Any] = {"checks": {}, "passed": True}
    async with driver.session() as session:
        for name, cypher in required_checks.items():
            result = await session.run(cypher)
            record = await result.single()
            count = int(record["count"]) if record else 0
            if name == "bpo_not_topical_or_oral_antibiotic":
                passed = count == 0
            else:
                passed = count > 0
            results["checks"][name] = {"count": count, "passed": passed}
            results["passed"] = results["passed"] and passed

        label_counts: dict[str, int] = {}
        for label in ENTITY_GRAPH_LABELS:
            result = await session.run(f"MATCH (n:{label}) RETURN count(n) AS count")
            record = await result.single()
            label_counts[label] = int(record["count"]) if record else 0
        results["nodes_by_label"] = label_counts

        relationship_counts: dict[str, int] = {}
        for rel_type in ENTITY_GRAPH_RELATIONSHIPS:
            result = await session.run(f"MATCH ()-[r:{rel_type}]->() RETURN count(r) AS count")
            record = await result.single()
            relationship_counts[rel_type] = int(record["count"]) if record else 0
        results["relationships_by_type"] = relationship_counts

    return results


def sanitize_neo4j_properties(properties: dict[str, Any]) -> dict[str, Any]:
    """Return Neo4j-safe flat properties.

    Neo4j properties may only be primitive values or arrays of primitive values.
    Nested maps/lists are preserved as deterministic JSON strings using a
    ``*_json`` property, e.g. ``metadata`` becomes ``metadata_json``.
    """

    sanitized: dict[str, Any] = {}
    for key, value in properties.items():
        if value is None:
            continue

        if _is_primitive_neo4j_value(value):
            sanitized[key] = value
            continue

        if isinstance(value, list) and all(
            _is_primitive_neo4j_value(item) for item in value
        ):
            sanitized[key] = value
            continue

        sanitized[f"{key}_json"] = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )

    return sanitized


def _is_primitive_neo4j_value(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool))


def _safe_label(label: str) -> str:
    if label not in ENTITY_GRAPH_LABELS:
        raise ValueError(f"Unsupported entity graph label: {label}")
    return label


def _safe_relationship(relationship: str) -> str:
    if relationship not in ENTITY_GRAPH_RELATIONSHIPS:
        raise ValueError(f"Unsupported entity graph relationship: {relationship}")
    return relationship


__all__ = [
    "apply_entity_graph_schema",
    "get_neo4j_driver",
    "sanitize_neo4j_properties",
    "upsert_entity_graph",
    "validate_entity_graph",
]
