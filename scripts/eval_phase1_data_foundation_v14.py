"""Read-only Phase 1 data foundation audit for Audit 14.

The audit inspects source text, ingestion manifest, Qdrant collections, Neo4j
entity graph, and taxonomy aliases without mutating runtime stores.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import statistics
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
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

from src.database.vector_store import qdrant_client_kwargs  # noqa: E402
from src.knowledge.graph_index import get_neo4j_driver  # noqa: E402
from src.knowledge.normalizer import DrugEntityNormalizer  # noqa: E402


CRITICAL_ENTITIES: dict[str, dict[str, Any]] = {
    "Tazorac": {
        "entity_type": "drug_product",
        "aliases": ["tazorac"],
        "required_terms": ["Tazorac", "tazarotene"],
        "required_relations": [("Tazorac", "HAS_ACTIVE_INGREDIENT", "tazarotene")],
    },
    "Differin": {
        "entity_type": "drug_product",
        "aliases": ["differin"],
        "required_terms": ["Differin", "adapalene"],
        "required_relations": [("Differin", "HAS_ACTIVE_INGREDIENT", "adapalene")],
    },
    "Epiduo": {
        "entity_type": "drug_product",
        "aliases": ["epiduo"],
        "required_terms": ["Epiduo", "adapalene", "benzoyl peroxide"],
        "required_relations": [
            ("Epiduo", "HAS_ACTIVE_INGREDIENT", "adapalene"),
            ("Epiduo", "HAS_ACTIVE_INGREDIENT", "benzoyl_peroxide"),
        ],
    },
    "tazarotene": {
        "entity_type": "active_ingredient",
        "aliases": ["tazarotene", "tazaroten"],
        "required_terms": ["tazarotene"],
        "required_relations": [("tazarotene", "BELONGS_TO_CLASS", "topical_retinoid")],
    },
    "adapalene": {
        "entity_type": "active_ingredient",
        "aliases": ["adapalene", "adapalen"],
        "required_terms": ["adapalene"],
        "required_relations": [("adapalene", "BELONGS_TO_CLASS", "topical_retinoid")],
    },
    "benzoyl_peroxide": {
        "entity_type": "active_ingredient",
        "aliases": ["benzoyl peroxide", "benzoyl_peroxide", "bp", "bpo"],
        "required_terms": ["benzoyl peroxide"],
        "required_relations": [("benzoyl_peroxide", "BELONGS_TO_CLASS", "benzoyl_peroxide")],
    },
    "tretinoin": {
        "entity_type": "active_ingredient",
        "aliases": ["tretinoin"],
        "required_terms": ["tretinoin"],
        "required_relations": [("tretinoin", "BELONGS_TO_CLASS", "topical_retinoid")],
    },
    "isotretinoin": {
        "entity_type": "active_ingredient",
        "aliases": ["isotretinoin"],
        "required_terms": ["isotretinoin"],
        "required_relations": [("isotretinoin", "BELONGS_TO_CLASS", "oral_retinoid")],
    },
    "clindamycin": {
        "entity_type": "active_ingredient",
        "aliases": ["clindamycin"],
        "required_terms": ["clindamycin"],
        "required_relations": [("clindamycin", "BELONGS_TO_CLASS", "topical_antibiotic")],
    },
    "erythromycin": {
        "entity_type": "active_ingredient",
        "aliases": ["erythromycin"],
        "required_terms": ["erythromycin"],
        "required_relations": [],
    },
    "salicylic_acid": {
        "entity_type": "active_ingredient",
        "aliases": ["salicylic acid", "salicylic_acid"],
        "required_terms": ["salicylic acid"],
        "required_relations": [],
    },
    "azelaic_acid": {
        "entity_type": "active_ingredient",
        "aliases": ["azelaic acid", "azelaic_acid"],
        "required_terms": ["azelaic acid"],
        "required_relations": [("azelaic_acid", "BELONGS_TO_CLASS", "azelaic_acid")],
    },
    "topical_retinoid": {
        "entity_type": "drug_class",
        "aliases": ["topical retinoid", "retinoid", "retinoid bôi"],
        "required_terms": ["retinoid"],
        "required_relations": [],
    },
    "topical_antibiotic": {
        "entity_type": "drug_class",
        "aliases": ["topical antibiotic", "kháng sinh bôi", "kháng sinh bôi tại chỗ"],
        "required_terms": ["topical antibiotic", "kháng sinh bôi"],
        "required_relations": [],
    },
    "pregnancy": {
        "entity_type": "safety_context",
        "aliases": ["pregnancy", "pregnant", "mang thai", "thai kỳ"],
        "required_terms": ["pregnancy", "mang thai"],
        "required_relations": [],
    },
    "breastfeeding": {
        "entity_type": "safety_context",
        "aliases": ["breastfeeding", "cho con bú"],
        "required_terms": ["breastfeeding", "cho con bú"],
        "required_relations": [],
    },
    "severe_acne": {
        "entity_type": "safety_context",
        "aliases": ["severe acne", "mụn nặng", "mụn cục", "mụn nang"],
        "required_terms": ["severe acne", "mụn nặng", "mụn cục", "mụn nang"],
        "required_relations": [],
    },
    "acne_vulgaris": {
        "entity_type": "condition",
        "aliases": ["acne vulgaris", "mụn trứng cá", "trứng cá"],
        "required_terms": ["acne vulgaris", "mụn trứng cá"],
        "required_relations": [],
    },
}


ACTION_LABELS = {
    "A": "NO REINGESTION",
    "B": "TAXONOMY/ALIAS FIX ONLY",
    "C": "TARGETED REINGESTION",
    "D": "ENTITY INDEX REBUILD",
    "E": "CONTROLLED FULL REINGESTION",
    "F": "SOURCE DATA EXPANSION REQUIRED",
}


@dataclass(frozen=True)
class StoreCoverage:
    source_present: bool
    knowledge_present: bool
    entity_present: bool
    graph_present: bool
    runtime_detected: bool
    manifest_ok: bool = True


def normalize_for_search(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text or "")
    without_marks = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    without_marks = without_marks.replace("đ", "d").replace("Đ", "D")
    without_marks = re.sub(r"[_\-]+", " ", without_marks.lower())
    return re.sub(r"\s+", " ", without_marks).strip()


def text_contains_any(text: str, terms: list[str]) -> bool:
    normalized = normalize_for_search(text)
    return any(normalized_contains_term(normalized, term) for term in terms)


def normalized_contains_term(normalized_text: str, term: str) -> bool:
    normalized_term = normalize_for_search(term)
    if not normalized_term:
        return False
    pattern = rf"(?<![a-z0-9]){re.escape(normalized_term)}(?![a-z0-9])"
    return re.search(pattern, normalized_text) is not None


def classify_fact_presence(evidence_count: int, *, ambiguous: bool = False, conflicting: bool = False) -> str:
    if evidence_count <= 0:
        return "fact absent"
    if conflicting:
        return "fact present but conflicting"
    if ambiguous:
        return "fact present but ambiguous"
    return "fact present and correct"


def infer_phase1_action(coverage: StoreCoverage) -> str:
    """Infer one Audit 14 action label from cross-store evidence."""

    if not coverage.source_present:
        return "F"
    if not coverage.manifest_ok:
        return "E"
    if coverage.source_present and not coverage.knowledge_present:
        return "C"
    if coverage.knowledge_present and (not coverage.entity_present or not coverage.graph_present):
        return "D"
    if coverage.entity_present and coverage.graph_present and not coverage.runtime_detected:
        return "B"
    return "A"


def full_reingestion_guard(report: dict[str, Any]) -> bool:
    manifest = report.get("manifest_integrity") or {}
    knowledge = (report.get("qdrant") or {}).get("knowledge") or {}
    return bool(
        manifest.get("hash_mismatches")
        or manifest.get("duplicate_document_ids")
        or manifest.get("duplicate_point_ids")
        or knowledge.get("duplicate_chunk_ids")
        or knowledge.get("missing_required_metadata")
    )


def sha_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def source_files() -> list[Path]:
    roots = [PROJECT_ROOT / "sample_data", PROJECT_ROOT / "data" / "cache", PROJECT_ROOT / "data" / "taxonomy"]
    extensions = {".json", ".jsonl", ".md", ".txt", ".yaml", ".yml", ".pdf"}
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in extensions:
                files.append(path)
    return sorted(files)


def read_text_for_search(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def build_source_inventory() -> dict[str, Any]:
    files = source_files()
    evidence: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for path in files:
        text = read_text_for_search(path)
        for entity, spec in CRITICAL_ENTITIES.items():
            terms = spec.get("aliases") or spec.get("required_terms") or [entity]
            if text_contains_any(text, list(terms)):
                evidence[entity].append(
                    {
                        "path": str(path.relative_to(PROJECT_ROOT)),
                        "size": path.stat().st_size,
                        "sha256": sha_file(path) if path.suffix.lower() != ".pdf" else None,
                        "excerpt": excerpt_around_terms(text, list(terms)),
                    }
                )
    return {
        "source_files_count": len(files),
        "source_files": [
            {
                "path": str(path.relative_to(PROJECT_ROOT)),
                "size": path.stat().st_size,
                "modified_time": path.stat().st_mtime,
            }
            for path in files
        ],
        "entity_evidence": dict(evidence),
    }


def excerpt_around_terms(text: str, terms: list[str], limit: int = 320) -> str:
    collapsed = " ".join((text or "").split())
    normalized = normalize_for_search(collapsed)
    positions = [
        normalized.find(normalize_for_search(term))
        for term in terms
        if normalize_for_search(term) in normalized
    ]
    if not positions:
        return ""
    start = max(0, min(positions) - limit // 3)
    return collapsed[start : start + limit].strip()


def manifest_integrity(manifest_path: Path) -> dict[str, Any]:
    manifest = load_json(manifest_path)
    docs = manifest.get("documents") or {}
    point_ids: list[str] = []
    document_ids: list[str] = []
    missing_sources: list[str] = []
    hash_mismatches: list[str] = []
    completed_empty_points: list[str] = []
    status_counts = Counter()
    source_type_counts = Counter()
    qdrant_indexed_by_source: dict[str, int] = {}

    for source_path, entry in docs.items():
        status_counts[str(entry.get("status") or "unknown")] += 1
        source_type_counts[str(entry.get("source_type") or "unknown")] += 1
        document_id = str(entry.get("document_id") or "")
        if document_id:
            document_ids.append(document_id)
        ids = [str(item) for item in entry.get("qdrant_point_ids") or []]
        point_ids.extend(ids)
        qdrant_indexed_by_source[source_path] = len(ids)
        path = Path(source_path)
        if not path.exists():
            missing_sources.append(source_path)
            continue
        content_hash = entry.get("content_hash")
        if content_hash and path.is_file() and sha_file(path) != content_hash:
            hash_mismatches.append(source_path)
        if str(entry.get("status") or "").startswith("completed") and entry.get("qdrant_indexed") and not ids:
            completed_empty_points.append(source_path)

    duplicate_point_ids = sorted(pid for pid, count in Counter(point_ids).items() if count > 1)
    duplicate_document_ids = sorted(doc_id for doc_id, count in Counter(document_ids).items() if count > 1)
    return {
        "path": str(manifest_path),
        "exists": manifest_path.exists(),
        "document_count": len(docs),
        "status_counts": dict(status_counts),
        "source_type_counts": dict(source_type_counts),
        "total_qdrant_point_ids": len(point_ids),
        "duplicate_point_ids": duplicate_point_ids,
        "duplicate_document_ids": duplicate_document_ids,
        "missing_sources": missing_sources,
        "hash_mismatches": hash_mismatches,
        "completed_empty_points": completed_empty_points,
        "qdrant_indexed_by_source": qdrant_indexed_by_source,
    }


def scroll_collection(collection: str) -> list[tuple[Any, dict[str, Any]]]:
    from qdrant_client import QdrantClient  # type: ignore[import]

    client = QdrantClient(**qdrant_client_kwargs())
    points: list[tuple[Any, dict[str, Any]]] = []
    offset = None
    try:
        while True:
            batch, offset = client.scroll(
                collection_name=collection,
                limit=256,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            points.extend((point.id, point.payload or {}) for point in batch)
            if offset is None:
                break
    finally:
        client.close()
    return points


def payload_text(payload: dict[str, Any]) -> str:
    values = [
        payload.get("text"),
        payload.get("content"),
        payload.get("page_content"),
        payload.get("canonical_name"),
        " ".join(payload.get("aliases") or []),
        " ".join(payload.get("active_ingredients") or []),
        " ".join(payload.get("drug_class") or []),
    ]
    return "\n".join(str(value) for value in values if value)


def collection_summary(collection: str, points: list[tuple[Any, dict[str, Any]]]) -> dict[str, Any]:
    chunk_ids: list[str] = []
    document_ids: list[str] = []
    source_paths: list[str] = []
    text_lengths: list[int] = []
    missing = Counter()
    duplicate_text = Counter()
    matches: dict[str, list[dict[str, Any]]] = defaultdict(list)
    match_counts: Counter[str] = Counter()

    for point_id, payload in points:
        text = payload_text(payload)
        text_lengths.append(len(text))
        if text:
            duplicate_text[hashlib.sha256(" ".join(text.split()).encode("utf-8")).hexdigest()[:16]] += 1
        for field in ("document_id", "source_path", "chunk_id"):
            if not payload.get(field):
                missing[field] += 1
        if payload.get("chunk_id"):
            chunk_ids.append(str(payload["chunk_id"]))
        if payload.get("document_id"):
            document_ids.append(str(payload["document_id"]))
        if payload.get("source_path"):
            source_paths.append(str(payload["source_path"]))
        for entity, spec in CRITICAL_ENTITIES.items():
            terms = list(spec.get("aliases") or spec.get("required_terms") or [entity])
            if text_contains_any(text, terms):
                match_counts[entity] += 1
                if len(matches[entity]) < 8:
                    matches[entity].append(
                        {
                            "point_id": str(point_id),
                            "chunk_id": payload.get("chunk_id"),
                            "document_id": payload.get("document_id"),
                            "source_path": payload.get("source_path"),
                            "source_file": payload.get("source_file"),
                            "canonical_name": payload.get("canonical_name"),
                            "entity_type": payload.get("entity_type"),
                            "excerpt": excerpt_around_terms(text, terms),
                        }
                    )

    duplicates = sorted(item for item, count in Counter(chunk_ids).items() if count > 1)
    duplicate_text_hashes = sorted(item for item, count in duplicate_text.items() if count > 1)
    return {
        "collection": collection,
        "total_points": len(points),
        "unique_document_ids": len(set(document_ids)),
        "unique_source_paths": len(set(source_paths)),
        "duplicate_chunk_ids": duplicates,
        "duplicate_text_hash_count": len(duplicate_text_hashes),
        "missing_required_metadata": dict(missing),
        "text_length_chars": percentiles(text_lengths),
        "entity_matches": {
            entity: {"count": match_counts[entity], "sample_count": len(samples), "samples": samples}
            for entity, samples in matches.items()
        },
    }


def percentiles(values: list[int]) -> dict[str, float]:
    if not values:
        return {}
    ordered = sorted(values)
    return {
        "min": float(ordered[0]),
        "p50": float(ordered[round((len(ordered) - 1) * 0.5)]),
        "p90": float(ordered[round((len(ordered) - 1) * 0.9)]),
        "p95": float(ordered[round((len(ordered) - 1) * 0.95)]),
        "max": float(ordered[-1]),
        "mean": round(float(statistics.mean(ordered)), 2),
    }


def taxonomy_coverage() -> dict[str, Any]:
    normalizer = DrugEntityNormalizer()
    aliases = sorted(normalizer.alias_index)
    coverage: dict[str, Any] = {}
    query = "Tazorac, Differin và Epiduo khác nhau về hoạt chất như thế nào?"
    expansion = normalizer.expand_query(query)
    for entity, spec in CRITICAL_ENTITIES.items():
        alias_hits = []
        for alias in spec.get("aliases") or [entity]:
            alias_hits.extend(card.canonical_name for card in normalizer.normalize_mention(alias))
        coverage[entity] = {
            "alias_present": bool(alias_hits),
            "resolved_canonical_names": sorted(set(alias_hits)),
        }
    return {
        "taxonomy_path": str(normalizer.taxonomy_path),
        "taxonomy_version": normalizer.taxonomy_version,
        "alias_count": len(aliases),
        "coverage": coverage,
        "tazorac_case_expansion": {
            "expanded_terms": expansion.get("expanded_terms"),
            "normalized_entities": [
                {
                    "canonical_name": item.get("canonical_name"),
                    "entity_type": item.get("entity_type"),
                    "active_ingredients": item.get("active_ingredients"),
                    "drug_class": item.get("drug_class"),
                }
                for item in expansion.get("normalized_entities", [])
            ],
        },
    }


async def neo4j_coverage() -> dict[str, Any]:
    driver = get_neo4j_driver()
    try:
        async with driver.session() as session:
            labels_result = await session.run("MATCH (n) RETURN labels(n) AS labels, count(*) AS total ORDER BY total DESC")
            label_rows = [dict(record) async for record in labels_result]
            rel_result = await session.run("MATCH ()-[r]->() RETURN type(r) AS relation, count(*) AS total ORDER BY total DESC")
            rel_rows = [dict(record) async for record in rel_result]
            node_result = await session.run(
                """
                MATCH (n)
                WHERE toLower(coalesce(n.canonical_name, '')) IN $names
                   OR any(alias IN coalesce(n.aliases, []) WHERE toLower(alias) IN $names)
                RETURN labels(n) AS labels, n.canonical_name AS canonical_name,
                       n.entity_type AS entity_type, n.aliases AS aliases,
                       n.entity_id AS entity_id
                ORDER BY canonical_name
                """,
                names=[normalize_for_search(name) for name in CRITICAL_ENTITIES],
            )
            nodes = [dict(record) async for record in node_result]
            all_node_result = await session.run(
                """
                MATCH (n)
                RETURN labels(n) AS labels, n.canonical_name AS canonical_name,
                       n.entity_type AS entity_type, n.aliases AS aliases,
                       n.entity_id AS entity_id
                ORDER BY canonical_name
                """
            )
            all_nodes = [dict(record) async for record in all_node_result]
            product_result = await session.run(
                """
                MATCH (p:DrugProduct)-[r:HAS_ACTIVE_INGREDIENT]->(a:ActiveIngredient)
                RETURN p.canonical_name AS product, type(r) AS relation, a.canonical_name AS ingredient
                ORDER BY product, ingredient
                """
            )
            product_rels = [dict(record) async for record in product_result]
            class_result = await session.run(
                """
                MATCH (a:ActiveIngredient)-[r:BELONGS_TO_CLASS]->(c:DrugClass)
                RETURN a.canonical_name AS ingredient, type(r) AS relation, c.canonical_name AS class
                ORDER BY ingredient, class
                """
            )
            class_rels = [dict(record) async for record in class_result]
    finally:
        await driver.close()

    return {
        "labels": label_rows,
        "relationship_types": rel_rows,
        "critical_nodes": nodes,
        "all_nodes": all_nodes,
        "product_ingredient_relationships": product_rels,
        "ingredient_class_relationships": class_rels,
    }


def relation_exists(neo4j: dict[str, Any], relation: tuple[str, str, str]) -> bool:
    source, rel_type, target = relation
    source_norm = normalize_for_search(source)
    target_norm = normalize_for_search(target)
    if rel_type == "HAS_ACTIVE_INGREDIENT":
        for row in neo4j.get("product_ingredient_relationships", []):
            if normalize_for_search(str(row.get("product"))) == source_norm and normalize_for_search(str(row.get("ingredient"))) == target_norm:
                return True
    if rel_type == "BELONGS_TO_CLASS":
        for row in neo4j.get("ingredient_class_relationships", []):
            if normalize_for_search(str(row.get("ingredient"))) == source_norm and normalize_for_search(str(row.get("class"))) == target_norm:
                return True
    return False


def entity_collection_has(entity_points: list[tuple[Any, dict[str, Any]]], entity: str, spec: dict[str, Any]) -> bool:
    names = [entity, *list(spec.get("aliases") or [])]
    for _, payload in entity_points:
        if payload.get("entity_type") != spec.get("entity_type"):
            continue
        haystack = payload_text(payload)
        if text_contains_any(haystack, names):
            return True
    return False


def cross_store_entity_id_consistency(
    entity_points: list[tuple[Any, dict[str, Any]]],
    neo4j: dict[str, Any],
) -> dict[str, Any]:
    qdrant_ids: dict[tuple[str, str], str] = {}
    for _, payload in entity_points:
        entity_type = str(payload.get("entity_type") or "")
        canonical_name = str(payload.get("canonical_name") or "")
        entity_id = str(payload.get("entity_id") or "")
        if entity_type and canonical_name and entity_id:
            qdrant_ids[(entity_type, normalize_for_search(canonical_name))] = entity_id

    neo4j_ids: dict[tuple[str, str], str] = {}
    for row in neo4j.get("all_nodes", []) or neo4j.get("critical_nodes", []) or []:
        entity_type = str(row.get("entity_type") or "")
        canonical_name = str(row.get("canonical_name") or "")
        entity_id = str(row.get("entity_id") or "")
        if entity_type and canonical_name and entity_id:
            neo4j_ids[(entity_type, normalize_for_search(canonical_name))] = entity_id

    shared = sorted(set(qdrant_ids) & set(neo4j_ids))
    mismatches = [
        {
            "entity_type": entity_type,
            "canonical_name": canonical_name,
            "qdrant_entity_id": qdrant_ids[(entity_type, canonical_name)],
            "neo4j_entity_id": neo4j_ids[(entity_type, canonical_name)],
        }
        for entity_type, canonical_name in shared
        if qdrant_ids[(entity_type, canonical_name)] != neo4j_ids[(entity_type, canonical_name)]
    ]
    return {
        "shared_entities": len(shared),
        "mismatches": mismatches,
        "qdrant_only": [f"{entity_type}:{name}" for entity_type, name in sorted(set(qdrant_ids) - set(neo4j_ids))],
        "neo4j_only": [f"{entity_type}:{name}" for entity_type, name in sorted(set(neo4j_ids) - set(qdrant_ids))],
    }


def build_entity_coverage_matrix(report: dict[str, Any]) -> dict[str, Any]:
    source_evidence = (report.get("source_coverage") or {}).get("entity_evidence") or {}
    knowledge_matches = ((report.get("qdrant") or {}).get("knowledge") or {}).get("entity_matches") or {}
    entity_matches = ((report.get("qdrant") or {}).get("entities") or {}).get("entity_matches") or {}
    taxonomy = ((report.get("taxonomy") or {}).get("coverage") or {})
    neo4j = report.get("neo4j") or {}
    rows: dict[str, Any] = {}

    for entity, spec in CRITICAL_ENTITIES.items():
        relations = spec.get("required_relations") or []
        relation_status = {f"{src}-{rel}->{dst}": relation_exists(neo4j, (src, rel, dst)) for src, rel, dst in relations}
        rows[entity] = {
            "entity_type": spec.get("entity_type"),
            "source_present": bool(source_evidence.get(entity)),
            "knowledge_present": bool(knowledge_matches.get(entity)),
            "entity_card_present": bool(entity_matches.get(entity)),
            "neo4j_relation_present": all(relation_status.values()) if relation_status else None,
            "alias_present": bool((taxonomy.get(entity) or {}).get("alias_present")),
            "runtime_resolved": (taxonomy.get(entity) or {}).get("resolved_canonical_names") or [],
            "relation_status": relation_status,
        }
    return rows


def diagnose_tazorac(report: dict[str, Any]) -> dict[str, Any]:
    matrix = report["entity_coverage_matrix"]
    tazorac = matrix["Tazorac"]
    tazarotene = matrix["tazarotene"]
    coverage = StoreCoverage(
        source_present=bool(tazorac["source_present"] or tazarotene["source_present"]),
        knowledge_present=bool(tazorac["knowledge_present"] or tazarotene["knowledge_present"]),
        entity_present=bool(tazorac["entity_card_present"] and tazarotene["entity_card_present"]),
        graph_present=bool(tazorac["neo4j_relation_present"] and tazarotene["neo4j_relation_present"]),
        runtime_detected=bool(tazorac["alias_present"] and tazarotene["alias_present"]),
        manifest_ok=not full_reingestion_guard(report),
    )
    action = infer_phase1_action(coverage)
    return {
        "source_corpus": coverage.source_present,
        "qdrant_knowledge": coverage.knowledge_present,
        "qdrant_entity": coverage.entity_present,
        "neo4j_graph": coverage.graph_present,
        "runtime_alias": coverage.runtime_detected,
        "manifest_ok": coverage.manifest_ok,
        "first_failing_stage": first_failing_stage(coverage),
        "recommended_action": f"{action}. {ACTION_LABELS[action]}",
    }


def first_failing_stage(coverage: StoreCoverage) -> str:
    if not coverage.source_present:
        return "source_corpus"
    if not coverage.manifest_ok:
        return "manifest_integrity"
    if not coverage.knowledge_present:
        return "qdrant_knowledge"
    if not coverage.entity_present:
        return "qdrant_entity"
    if not coverage.graph_present:
        return "neo4j_graph"
    if not coverage.runtime_detected:
        return "runtime_alias"
    return "post_phase1_runtime"


def write_report(path: Path, title: str, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {title}\n\n{body.rstrip()}\n", encoding="utf-8")


def md_table(headers: list[str], rows: list[list[Any]]) -> str:
    output = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        output.append("| " + " | ".join(str(value).replace("\n", " ") for value in row) + " |")
    return "\n".join(output)


def write_markdown_reports(report: dict[str, Any], reports_dir: Path) -> None:
    reports_dir.mkdir(parents=True, exist_ok=True)
    inventory = report["source_coverage"]
    write_report(
        reports_dir / "01_source_inventory.md",
        "Source Inventory",
        f"Source files scanned: {inventory['source_files_count']}\n\n"
        + md_table(
            ["Entity", "Evidence files"],
            [[entity, len(samples)] for entity, samples in sorted(inventory["entity_evidence"].items())],
        ),
    )

    manifest = report["manifest_integrity"]
    write_report(
        reports_dir / "02_manifest_integrity.md",
        "Manifest Integrity",
        json.dumps(
            {key: manifest[key] for key in manifest if key != "qdrant_indexed_by_source"},
            ensure_ascii=False,
            indent=2,
        ),
    )

    knowledge = report["qdrant"]["knowledge"]
    write_report(
        reports_dir / "03_qdrant_knowledge.md",
        "Qdrant Knowledge Collection",
        json.dumps(knowledge, ensure_ascii=False, indent=2),
    )

    entities = report["qdrant"]["entities"]
    write_report(
        reports_dir / "04_qdrant_entities.md",
        "Qdrant Entity Collection",
        json.dumps(entities, ensure_ascii=False, indent=2),
    )

    write_report(
        reports_dir / "05_neo4j_graph.md",
        "Neo4j Graph",
        json.dumps(report["neo4j"], ensure_ascii=False, indent=2),
    )

    write_report(
        reports_dir / "06_taxonomy_aliases.md",
        "Taxonomy Aliases",
        json.dumps(report["taxonomy"], ensure_ascii=False, indent=2),
    )

    matrix_rows = []
    for entity, row in report["entity_coverage_matrix"].items():
        matrix_rows.append(
            [
                entity,
                row["entity_type"],
                row["source_present"],
                row["knowledge_present"],
                row["entity_card_present"],
                row["neo4j_relation_present"],
                row["alias_present"],
            ]
        )
    write_report(
        reports_dir / "07_entity_coverage_matrix.md",
        "Entity Coverage Matrix",
        md_table(
            ["Entity", "Type", "Source", "Knowledge", "Entity card", "Neo4j relation", "Alias"],
            matrix_rows,
        ),
    )

    write_report(
        reports_dir / "08_source_quality.md",
        "Source Quality",
        "\n".join(
            [
                "Authority sources present include local PDFs, guideline-derived markdown cache, and web_raw_dataset.json.",
                "The audit does not infer trust solely from filename; it reports provenance paths and evidence excerpts only.",
                "Raw web records contain several product brand facts, including Tazorac/Tazarotene pregnancy safety mentions.",
            ]
        ),
    )

    write_report(
        reports_dir / "09_cross_store_consistency.md",
        "Cross-Store Consistency",
        json.dumps(report["tazorac_diagnosis"], ensure_ascii=False, indent=2),
    )

    recommendation = report["tazorac_diagnosis"]["recommended_action"]
    write_report(
        reports_dir / "10_phase1_recommendation.md",
        "Phase 1 Recommendation",
        "\n".join(
            [
                f"PHASE 1 ACTION REQUIRED: {recommendation}",
                "",
                f"First failing stage for Tazorac case: {report['tazorac_diagnosis']['first_failing_stage']}",
                "",
                "Do not delete runtime data. Do not run full ingestion as part of this audit.",
                "If approved, the next data action should be scoped to taxonomy/entity index and graph rebuild, not acne_knowledge re-ingestion.",
            ]
        ),
    )


async def run_audit(args: argparse.Namespace) -> dict[str, Any]:
    knowledge_points = scroll_collection(args.chunk_collection)
    entity_points = scroll_collection(args.entity_collection)
    report: dict[str, Any] = {
        "source_coverage": build_source_inventory(),
        "manifest_integrity": manifest_integrity(PROJECT_ROOT / args.manifest_path),
        "qdrant": {
            "knowledge": collection_summary(args.chunk_collection, knowledge_points),
            "entities": collection_summary(args.entity_collection, entity_points),
        },
        "taxonomy": taxonomy_coverage(),
        "neo4j": await neo4j_coverage(),
    }
    report["entity_coverage_matrix"] = build_entity_coverage_matrix(report)
    report["cross_store_entity_id_consistency"] = cross_store_entity_id_consistency(entity_points, report["neo4j"])
    report["tazorac_diagnosis"] = diagnose_tazorac(report)
    report["full_reingestion_guard"] = full_reingestion_guard(report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Audit 14 Phase 1 data foundation evaluator.")
    parser.add_argument("--chunk-collection", default=os.getenv("QDRANT_COLLECTION_NAME", "acne_knowledge"))
    parser.add_argument("--entity-collection", default=os.getenv("ENTITY_QDRANT_COLLECTION_NAME", "acne_entities_v1"))
    parser.add_argument("--manifest-path", default="data/ingestion_manifest.json")
    parser.add_argument("--output", default="artifacts/audit14/phase1_data_foundation_v14.json")
    parser.add_argument("--reports-dir", default="reports/audit14")
    args = parser.parse_args()

    report = asyncio.run(run_audit(args))
    output = PROJECT_ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown_reports(report, PROJECT_ROOT / args.reports_dir)

    print(json.dumps({
        "source_files": report["source_coverage"]["source_files_count"],
        "manifest_entries": report["manifest_integrity"]["document_count"],
        "qdrant_knowledge_points": report["qdrant"]["knowledge"]["total_points"],
        "qdrant_entity_points": report["qdrant"]["entities"]["total_points"],
        "neo4j_nodes_by_label": report["neo4j"]["labels"],
        "tazorac_diagnosis": report["tazorac_diagnosis"],
        "full_reingestion_guard": report["full_reingestion_guard"],
        "output": str(output),
        "reports_dir": str(PROJECT_ROOT / args.reports_dir),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
