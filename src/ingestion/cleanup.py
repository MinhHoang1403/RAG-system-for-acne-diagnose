"""Safe cleanup helpers for incremental ingestion re-runs."""

from __future__ import annotations

import logging
import os
from typing import Any

from src.knowledge.versioning import get_knowledge_versions

logger = logging.getLogger(__name__)

CLEANUP_VERSION = "qdrant_cleanup_v1"


def _env_str(name: str, default: str = "") -> str:
    value = os.getenv(name, "").strip()
    return value or default


def _chunk_collection_names() -> set[str]:
    qdrant_collection = _env_str("QDRANT_COLLECTION_NAME", "acne_knowledge")
    chunk_collection = _env_str("CHUNK_QDRANT_COLLECTION_NAME", "")
    names = {qdrant_collection}
    if chunk_collection and chunk_collection != "acne_chunks_v1":
        names.add(chunk_collection)
    return {name for name in names if name}


def _entity_collection_name() -> str:
    return _env_str("ENTITY_QDRANT_COLLECTION_NAME", "acne_entities_v1")


def is_safe_chunk_collection_for_cleanup(collection_name: str) -> bool:
    """Return True only for configured chunk collections, never entity collections."""

    normalized = (collection_name or "").strip()
    if not normalized:
        return False
    if normalized == _entity_collection_name():
        return False
    if "entities" in normalized.lower():
        return False
    return normalized in _chunk_collection_names()


def _dedupe_point_ids(raw_ids: Any) -> list[str]:
    if not isinstance(raw_ids, list):
        return []

    seen: set[str] = set()
    point_ids: list[str] = []
    for raw_id in raw_ids:
        point_id = str(raw_id).strip()
        if not point_id or point_id in seen:
            continue
        seen.add(point_id)
        point_ids.append(point_id)
    return point_ids


def build_qdrant_cleanup_plan(
    *,
    collection_name: str,
    manifest_record: dict[str, Any] | None,
    expected_document_id: str,
    expected_source_path: str | None = None,
) -> dict[str, Any]:
    """Build a deletion plan without touching Qdrant."""

    record = manifest_record or {}
    collection = (collection_name or "").strip()
    document_id = (expected_document_id or "").strip()
    source_path = (expected_source_path or "").strip() or None

    plan: dict[str, Any] = {
        "cleanup_version": CLEANUP_VERSION,
        "collection_name": collection,
        "document_id": document_id,
        "source_path": source_path,
        "safe": False,
        "cleanup_required": False,
        "mode": "blocked",
        "point_ids": [],
        "point_count": 0,
        "filter": None,
        "reason": "",
    }

    if not is_safe_chunk_collection_for_cleanup(collection):
        plan["reason"] = (
            "blocked unsafe Qdrant collection for chunk cleanup: "
            f"{collection or '<empty>'}"
        )
        return plan

    if not document_id:
        plan["reason"] = "blocked cleanup without expected_document_id"
        return plan

    record_document_id = str(record.get("document_id") or "").strip()
    if record_document_id and record_document_id != document_id:
        plan["reason"] = (
            "blocked cleanup because manifest document_id does not match "
            "the current source document"
        )
        return plan

    point_ids = _dedupe_point_ids(record.get("qdrant_point_ids", []))
    if point_ids:
        plan.update(
            {
                "safe": True,
                "cleanup_required": True,
                "mode": "ids",
                "point_ids": point_ids,
                "point_count": len(point_ids),
                "reason": "delete stored qdrant_point_ids",
            }
        )
        return plan

    kb_version = str(
        record.get("kb_version")
        or get_knowledge_versions().get("kb_version")
        or ""
    ).strip()
    conditions: list[dict[str, Any]] = [
        {"key": "document_id", "match": {"value": document_id}},
    ]
    if source_path:
        conditions.append({"key": "source_path", "match": {"value": source_path}})
    if kb_version:
        conditions.append({"key": "kb_version", "match": {"value": kb_version}})

    plan.update(
        {
            "safe": True,
            "cleanup_required": True,
            "mode": "filter",
            "filter": {"must": conditions},
            "kb_version": kb_version,
            "reason": "delete by scoped document_id/source_path/kb_version filter",
        }
    )
    return plan


def _qdrant_filter_from_plan(plan: dict[str, Any]) -> Any:
    from qdrant_client.models import FieldCondition, Filter, MatchValue  # type: ignore

    raw_filter = plan.get("filter") or {}
    conditions = []
    for condition in raw_filter.get("must", []):
        key = condition.get("key")
        value = (condition.get("match") or {}).get("value")
        if key and value is not None:
            conditions.append(
                FieldCondition(key=str(key), match=MatchValue(value=value))
            )
    return Filter(must=conditions)


async def cleanup_previous_qdrant_points(
    *,
    qdrant_client: Any,
    collection_name: str,
    manifest_record: dict[str, Any] | None,
    expected_document_id: str,
    expected_source_path: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Delete old chunk points for one document using a guarded plan."""

    plan = build_qdrant_cleanup_plan(
        collection_name=collection_name,
        manifest_record=manifest_record,
        expected_document_id=expected_document_id,
        expected_source_path=expected_source_path,
    )

    logger.info(
        "[QDRANT CLEANUP] collection=%s document_id=%s source_path=%s "
        "mode=%s point_count=%s dry_run=%s reason=%s",
        plan["collection_name"] or "<empty>",
        plan["document_id"] or "<empty>",
        plan.get("source_path") or "<none>",
        plan["mode"],
        plan["point_count"],
        dry_run,
        plan["reason"],
    )

    if not plan["safe"] or not plan["cleanup_required"] or dry_run:
        plan["deleted"] = False
        return plan

    if plan["mode"] == "ids":
        from qdrant_client.models import PointIdsList  # type: ignore

        await qdrant_client.delete(
            collection_name=plan["collection_name"],
            points_selector=PointIdsList(points=plan["point_ids"]),
        )
    elif plan["mode"] == "filter":
        await qdrant_client.delete(
            collection_name=plan["collection_name"],
            points_selector=_qdrant_filter_from_plan(plan),
        )
    else:
        plan["deleted"] = False
        return plan

    plan["deleted"] = True
    return plan


__all__ = [
    "CLEANUP_VERSION",
    "build_qdrant_cleanup_plan",
    "cleanup_previous_qdrant_points",
    "is_safe_chunk_collection_for_cleanup",
]
