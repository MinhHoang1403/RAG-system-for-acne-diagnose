"""Read-only corpus and manifest audit for Audit 13."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import sys
from collections import Counter, defaultdict
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


def _sha_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _text(payload: dict[str, Any]) -> str:
    return str(payload.get("text") or payload.get("content") or payload.get("page_content") or "")


def _percentiles(values: list[int]) -> dict[str, float]:
    if not values:
        return {}
    ordered = sorted(values)
    def pct(p: float) -> float:
        if len(ordered) == 1:
            return float(ordered[0])
        index = round((len(ordered) - 1) * p)
        return float(ordered[index])
    return {
        "min": float(ordered[0]),
        "p50": pct(0.50),
        "p90": pct(0.90),
        "p95": pct(0.95),
        "max": float(ordered[-1]),
        "mean": round(float(statistics.mean(ordered)), 2),
    }


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"manifest_exists": False, "documents": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    data["manifest_exists"] = True
    return data


def _manifest_summary(manifest_path: Path) -> dict[str, Any]:
    manifest = _load_manifest(manifest_path)
    docs = manifest.get("documents") or {}
    point_ids: list[str] = []
    missing_sources = []
    hash_mismatches = []
    completed_empty_points = []
    status_counts = Counter()
    source_types = Counter()
    document_ids = []

    for source_path, entry in docs.items():
        status = str(entry.get("status") or "")
        status_counts[status] += 1
        source_types[str(entry.get("source_type") or "unknown")] += 1
        document_ids.append(str(entry.get("document_id") or ""))
        path = Path(source_path)
        if not path.exists():
            missing_sources.append(source_path)
        elif entry.get("content_hash"):
            actual = _sha_file(path)
            if actual != entry.get("content_hash"):
                hash_mismatches.append(source_path)
        ids = [str(item) for item in entry.get("qdrant_point_ids") or []]
        point_ids.extend(ids)
        if status.startswith("completed") and entry.get("qdrant_indexed") and not ids:
            completed_empty_points.append(source_path)

    duplicated_point_ids = [pid for pid, count in Counter(point_ids).items() if count > 1]
    duplicated_document_ids = [doc_id for doc_id, count in Counter(document_ids).items() if doc_id and count > 1]
    return {
        "path": str(manifest_path),
        "manifest_exists": manifest.get("manifest_exists", False),
        "document_count": len(docs),
        "status_counts": dict(status_counts),
        "source_type_counts": dict(source_types),
        "total_qdrant_point_ids": len(point_ids),
        "duplicate_point_ids": duplicated_point_ids[:20],
        "duplicate_document_ids": duplicated_document_ids[:20],
        "missing_sources": missing_sources,
        "hash_mismatches": hash_mismatches,
        "completed_empty_points": completed_empty_points,
    }


def _scroll_collection(collection: str) -> list[tuple[Any, dict[str, Any]]]:
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


def audit_collection(collection: str) -> dict[str, Any]:
    points = _scroll_collection(collection)
    chunk_ids: list[str] = []
    document_ids: list[str] = []
    content_hashes: list[str] = []
    source_paths: list[str] = []
    source_files: list[str] = []
    source_types = Counter()
    languages = Counter()
    missing_metadata = Counter()
    empty_chunks = []
    too_short_chunks = []
    oversized_chunks = []
    text_hashes = Counter()
    text_lengths: list[int] = []
    sample_titles = {}

    required = ["document_id", "source_path", "chunk_id"]
    for point_id, payload in points:
        text = _text(payload)
        text_len = len(text)
        text_lengths.append(text_len)
        text_hash = hashlib.sha256(" ".join(text.split()).encode("utf-8")).hexdigest()[:16] if text else ""
        if text_hash:
            text_hashes[text_hash] += 1
        if not text.strip():
            empty_chunks.append(str(point_id))
        if 0 < text_len < 80:
            too_short_chunks.append(str(point_id))
        if text_len > 6000:
            oversized_chunks.append(str(point_id))
        for field in required:
            if not payload.get(field):
                missing_metadata[field] += 1
        if payload.get("chunk_id"):
            chunk_ids.append(str(payload.get("chunk_id")))
        if payload.get("document_id"):
            document_ids.append(str(payload.get("document_id")))
        if payload.get("content_hash"):
            content_hashes.append(str(payload.get("content_hash")))
        if payload.get("source_path"):
            source_paths.append(str(payload.get("source_path")))
        if payload.get("source_file"):
            source_files.append(str(payload.get("source_file")))
        source_types[str(payload.get("source_type") or "unknown")] += 1
        languages[str(payload.get("language") or "unknown")] += 1
        source = str(payload.get("source_file") or payload.get("source_path") or "unknown")
        if source not in sample_titles:
            sample_titles[source] = payload.get("document_title") or payload.get("title") or payload.get("header") or ""

    duplicate_chunk_ids = [item for item, count in Counter(chunk_ids).items() if count > 1]
    duplicate_text_hashes = [item for item, count in text_hashes.items() if count > 1]
    return {
        "collection": collection,
        "total_points": len(points),
        "unique_documents": len(set(document_ids)),
        "unique_source_paths": len(set(source_paths)),
        "unique_source_files": len(set(source_files)),
        "duplicate_chunk_ids": duplicate_chunk_ids[:50],
        "duplicate_text_hash_count": len(duplicate_text_hashes),
        "duplicate_text_hash_samples": duplicate_text_hashes[:20],
        "empty_chunks": empty_chunks[:20],
        "too_short_chunks_count": len(too_short_chunks),
        "too_short_chunk_samples": too_short_chunks[:20],
        "oversized_chunks": oversized_chunks[:20],
        "missing_metadata": dict(missing_metadata),
        "source_type_counts": dict(source_types),
        "language_counts": dict(languages),
        "text_length_chars": _percentiles(text_lengths),
        "source_title_samples": sample_titles,
        "content_hash_coverage": len(content_hashes),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Qdrant corpus audit.")
    parser.add_argument("--chunk-collection", default=os.getenv("QDRANT_COLLECTION_NAME", "acne_knowledge"))
    parser.add_argument("--entity-collection", default=os.getenv("ENTITY_QDRANT_COLLECTION_NAME", "acne_entities_v1"))
    parser.add_argument("--manifest-path", default="data/ingestion_manifest.json")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    report = {
        "manifest": _manifest_summary(PROJECT_ROOT / args.manifest_path),
        "collections": {
            args.chunk_collection: audit_collection(args.chunk_collection),
            args.entity_collection: audit_collection(args.entity_collection),
        },
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
