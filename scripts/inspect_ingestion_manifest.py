"""Inspect the ingestion manifest without connecting to external services."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


DEFAULT_MANIFEST_PATH = Path("data/ingestion_manifest.json")


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Manifest not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Manifest must be a JSON object")
    documents = data.get("documents", {})
    if not isinstance(documents, dict):
        raise ValueError("Manifest 'documents' must be an object")
    return data


def summarize_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    documents = manifest.get("documents", {})
    records = [
        record for record in documents.values()
        if isinstance(record, dict)
    ]

    status_counts = Counter(str(record.get("status") or "<missing>") for record in records)
    collection_counts = Counter(
        str(record.get("qdrant_collection") or "<missing>") for record in records
    )
    kb_versions = Counter(str(record.get("kb_version") or "<missing>") for record in records)
    embedding_models = Counter(
        str(record.get("embedding_model") or "<missing>") for record in records
    )
    source_types = Counter(str(record.get("source_type") or "<missing>") for record in records)

    missing_point_ids = [
        str(record.get("source_path") or key)
        for key, record in documents.items()
        if isinstance(record, dict) and not record.get("qdrant_point_ids")
    ]
    records_with_point_count = sum(
        1 for record in records
        if int(record.get("qdrant_point_count", 0) or 0) > 0
    )
    graph_skipped_records = [
        str(record.get("source_path") or key)
        for key, record in documents.items()
        if isinstance(record, dict)
        and (
            record.get("status") == "completed_with_graph_skipped"
            or record.get("graph_extraction_skipped") is True
        )
    ]
    qdrant_indexed_records = sum(
        1
        for record in records
        if record.get("qdrant_indexed") is True
        or int(record.get("qdrant_point_count", 0) or 0) > 0
    )

    return {
        "record_count": len(records),
        "missing_qdrant_point_ids": missing_point_ids,
        "records_with_qdrant_point_count": records_with_point_count,
        "qdrant_indexed_records": qdrant_indexed_records,
        "graph_skipped_records": graph_skipped_records,
        "status_counts": dict(status_counts),
        "qdrant_collections": dict(collection_counts),
        "kb_versions": dict(kb_versions),
        "embedding_models": dict(embedding_models),
        "source_types": dict(source_types),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect data/ingestion_manifest.json without Qdrant cleanup.",
    )
    parser.add_argument(
        "--manifest-path",
        type=Path,
        default=DEFAULT_MANIFEST_PATH,
        help="Path to ingestion manifest JSON.",
    )
    parser.add_argument(
        "--show-missing",
        action="store_true",
        help="Print records missing qdrant_point_ids.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = load_manifest(args.manifest_path)
    summary = summarize_manifest(manifest)

    print(f"Manifest: {args.manifest_path}")
    print(f"Records: {summary['record_count']}")
    print(f"Records with qdrant_point_count > 0: {summary['records_with_qdrant_point_count']}")
    print(f"Records qdrant_indexed: {summary['qdrant_indexed_records']}")
    print(f"Records missing qdrant_point_ids: {len(summary['missing_qdrant_point_ids'])}")
    print(f"Records with intentional graph skip: {len(summary['graph_skipped_records'])}")
    print(f"Status counts: {summary['status_counts']}")
    print(f"Source types: {summary['source_types']}")
    print(f"Qdrant collections: {summary['qdrant_collections']}")
    print(f"KB versions: {summary['kb_versions']}")
    print(f"Embedding models: {summary['embedding_models']}")

    if args.show_missing:
        for source_path in summary["missing_qdrant_point_ids"]:
            print(f"Missing qdrant_point_ids: {source_path}")
        for source_path in summary["graph_skipped_records"]:
            print(f"Graph intentionally skipped: {source_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
