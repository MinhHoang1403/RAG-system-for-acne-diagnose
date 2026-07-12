#!/usr/bin/env python3
"""
inspect_qdrant_v2_payload.py
============================
Phase 1.5 Step 5 – Inspect Qdrant ``acne_knowledge_v2`` payload.

Scrolls the first N points from the v2 collection and validates that
dermatology metadata (Step 2) and hierarchical metadata (Step 3)
fields are present.

No LlamaParse, no Neo4j, no LLM needed.  Only requires a running
Qdrant instance at http://localhost:6333.

Usage
-----
    python scripts/diagnostics/inspect_qdrant_v2_payload.py
    python scripts/diagnostics/inspect_qdrant_v2_payload.py --collection acne_knowledge
    python scripts/diagnostics/inspect_qdrant_v2_payload.py --limit 10
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Bootstrap
# ─────────────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env", override=False)
except ImportError:
    pass


# ─────────────────────────────────────────────────────────────────────────────
from src.database.vector_store import qdrant_client_kwargs

# Fields expected from Phase 1.5
DERMATOLOGY_FIELDS = [
    "domain_topic",
    "content_type",
    "concern",
    "ingredient",
    "skin_type",
    "body_area",
    "safety_context",
    "evidence_type",
    "metadata_confidence",
    "metadata_extraction_method",
]

HIERARCHICAL_FIELDS = [
    "parent_id",
    "chunk_level",
    "parent_header_path",
    "child_index_in_parent",
    "parent_text_hash",
    "section_char_length",
]

BASIC_FIELDS = [
    "source_file",
    "chunk_index",
    "chunk_id",
    "header",
]

ALL_DISPLAY_FIELDS = BASIC_FIELDS + DERMATOLOGY_FIELDS + HIERARCHICAL_FIELDS + ["graph_nodes"]

REQUIRED_FIELDS = [
    "domain_topic",
    "content_type",
    "concern",
    "metadata_confidence",
    "parent_id",
    "chunk_level",
    "parent_header_path",
    "child_index_in_parent",
]


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

async def inspect(collection: str, limit: int) -> int:
    try:
        from qdrant_client import AsyncQdrantClient  # type: ignore
    except ImportError:
        print("❌ qdrant-client not installed. Run: pip install qdrant-client")
        return 1

    client = AsyncQdrantClient(**qdrant_client_kwargs())

    try:
        # Check collection exists
        collections = await client.get_collections()
        existing = {c.name for c in collections.collections}

        if collection not in existing:
            print(f"❌ Collection '{collection}' does not exist in Qdrant.")
            print(f"   Available: {sorted(existing)}")
            return 1

        # Get collection info
        info = await client.get_collection(collection_name=collection)
        total_points = info.points_count
        print(f"  Collection : {collection}")
        print(f"  Total points: {total_points}")
        print()

        if total_points == 0:
            print("⚠️  Collection is empty — nothing to inspect.")
            return 1

        # Scroll points
        scroll_result = await client.scroll(
            collection_name=collection,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )

        points = scroll_result[0]
        print(f"  Scrolled {len(points)} points (limit={limit})\n")

        all_ok = True
        warnings: list[str] = []

        for i, point in enumerate(points):
            payload = point.payload or {}

            print("─" * 72)
            print(f"  Point {i}  (id={point.id})")
            print("─" * 72)

            # Text preview
            text = payload.get("text", "")
            preview = text[:200].replace("\n", " ")
            if len(text) > 200:
                preview += "…"
            print(f"  text          : {preview}")

            # Display fields
            for field in ALL_DISPLAY_FIELDS:
                if field == "text":
                    continue
                value = payload.get(field)
                if isinstance(value, list):
                    display = ", ".join(str(v) for v in value) if value else "—"
                elif value is None:
                    display = "—"
                else:
                    display = str(value)
                print(f"  {field:30s}: {display}")

            # Validate required fields
            for req in REQUIRED_FIELDS:
                if req not in payload:
                    msg = f"Point {i} (id={point.id}): missing '{req}'"
                    warnings.append(msg)
                    print(f"  ⚠️  WARNING: missing '{req}'")

            print()

        # ── Summary ────────────────────────────────────────────────────
        print("=" * 72)
        print("  Validation Summary")
        print("=" * 72)
        print(f"  Points inspected : {len(points)}")
        print(f"  Total points     : {total_points}")

        if warnings:
            print(f"\n  ⚠️  {len(warnings)} warnings:")
            for w in warnings:
                print(f"    - {w}")
            all_ok = False
        else:
            print(f"\n  ✅ All {len(points)} points have all required metadata fields.")

        # Check at least 1 point
        if len(points) == 0:
            print("  ❌ No points found!")
            all_ok = False

        print("=" * 72)
        return 0 if all_ok else 1

    finally:
        await client.close()


def _resolve_collection(cli_value: str | None) -> tuple[str, str]:
    """Resolve collection name with priority: CLI → env → fallback.

    Returns (collection_name, source_label).
    """
    _FALLBACK = "acne_knowledge_v2"

    if cli_value is not None:
        return cli_value, "CLI (--collection)"

    env1 = os.getenv("QDRANT_COLLECTION_NAME")
    if env1:
        return env1, "env(QDRANT_COLLECTION_NAME)"

    env2 = os.getenv("QDRANT_COLLECTION")
    if env2:
        return env2, "env(QDRANT_COLLECTION)"

    return _FALLBACK, f"fallback ('{_FALLBACK}')"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect Qdrant collection payload for Phase 1.5 metadata.",
    )
    parser.add_argument(
        "--collection",
        default=None,
        help="Qdrant collection name. Falls back to env QDRANT_COLLECTION_NAME, "
             "then QDRANT_COLLECTION, then 'acne_knowledge_v2'.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Number of points to inspect (default: 5)",
    )
    args = parser.parse_args()

    collection, source = _resolve_collection(args.collection)

    print("=" * 72)
    print("  Phase 1.5 Step 5 – Inspect Qdrant Payload")
    print("=" * 72)
    print(f"  Collection from : {source}")
    print(f"  Using collection: {collection}")

    return asyncio.run(inspect(collection, args.limit))


if __name__ == "__main__":
    raise SystemExit(main())
