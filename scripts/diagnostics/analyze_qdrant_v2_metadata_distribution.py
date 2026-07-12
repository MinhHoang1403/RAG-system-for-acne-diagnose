#!/usr/bin/env python3
"""
analyze_qdrant_v2_metadata_distribution.py
==========================================
Phase 1.5 Step 5.5 – Metadata distribution analysis for acne_knowledge_v2.

Scrolls ALL points in the collection and produces:
- Total point count
- Distribution of domain_topic, content_type, concern, ingredient, etc.
- Noisy chunk detection heuristics
- Sparse vector presence check

Usage
-----
    python scripts/diagnostics/analyze_qdrant_v2_metadata_distribution.py
    python scripts/diagnostics/analyze_qdrant_v2_metadata_distribution.py --collection acne_knowledge
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter
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
# Noisy chunk detection — uses canonical function from ingest pipeline
# ─────────────────────────────────────────────────────────────────────────────

from scripts.ingest_knowledge import is_noisy_chunk
from src.database.vector_store import qdrant_client_kwargs



# ─────────────────────────────────────────────────────────────────────────────
# Main analysis
# ─────────────────────────────────────────────────────────────────────────────

async def analyze(collection: str) -> int:
    try:
        from qdrant_client import AsyncQdrantClient  # type: ignore
    except ImportError:
        print("❌ qdrant-client not installed.")
        return 1

    client = AsyncQdrantClient(**qdrant_client_kwargs())

    try:
        # Check collection
        collections_resp = await client.get_collections()
        existing = {c.name for c in collections_resp.collections}
        if collection not in existing:
            print(f"❌ Collection '{collection}' not found. Available: {sorted(existing)}")
            return 1

        info = await client.get_collection(collection_name=collection)
        total_points = info.points_count
        print(f"  Collection       : {collection}")
        print(f"  Total points     : {total_points}")

        # Check sparse vector config
        sparse_config = info.config.params.sparse_vectors or {}
        print(f"  Sparse vectors   : {list(sparse_config.keys()) if sparse_config else 'NONE'}")

        if total_points == 0:
            print("⚠️  Empty collection.")
            return 1

        # Scroll ALL points
        all_points = []
        offset = None
        while True:
            scroll_result = await client.scroll(
                collection_name=collection,
                limit=100,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            points, next_offset = scroll_result
            all_points.extend(points)
            if next_offset is None:
                break
            offset = next_offset

        print(f"  Scrolled         : {len(all_points)} points\n")

        # ── Counters ────────────────────────────────────────────────
        domain_topic_ctr: Counter = Counter()
        content_type_ctr: Counter = Counter()
        concern_ctr: Counter = Counter()
        ingredient_ctr: Counter = Counter()
        safety_context_ctr: Counter = Counter()
        skin_type_ctr: Counter = Counter()
        body_area_ctr: Counter = Counter()
        header_ctr: Counter = Counter()

        zero_confidence = 0
        noisy_count = 0
        payload_noisy_count = 0
        noisy_details: list[str] = []

        # Fields missing
        missing_domain_topic = 0
        missing_parent_id = 0
        missing_content_type = 0

        # Sparse vector presence
        has_sparse = 0

        for point in all_points:
            payload = point.payload or {}
            text = payload.get("text", "")
            header = payload.get("header", "")

            # Domain topic
            dt = payload.get("domain_topic", [])
            if not dt:
                missing_domain_topic += 1
            if isinstance(dt, list):
                for v in dt:
                    domain_topic_ctr[v] += 1

            # Content type
            ct = payload.get("content_type", [])
            if not ct:
                missing_content_type += 1
            if isinstance(ct, list):
                for v in ct:
                    content_type_ctr[v] += 1

            # Concern
            cn = payload.get("concern", [])
            if isinstance(cn, list):
                for v in cn:
                    concern_ctr[v] += 1

            # Ingredient
            ig = payload.get("ingredient", [])
            if isinstance(ig, list):
                for v in ig:
                    ingredient_ctr[v] += 1

            # Safety context
            sc = payload.get("safety_context", [])
            if isinstance(sc, list):
                for v in sc:
                    safety_context_ctr[v] += 1

            # Skin type
            st = payload.get("skin_type", [])
            if isinstance(st, list):
                for v in st:
                    skin_type_ctr[v] += 1

            # Body area
            ba = payload.get("body_area", [])
            if isinstance(ba, list):
                for v in ba:
                    body_area_ctr[v] += 1

            # Header
            header_ctr[header or "(empty)"] += 1

            # Confidence
            conf = payload.get("metadata_confidence", None)
            if conf is not None and float(conf) == 0:
                zero_confidence += 1

            # Parent ID
            if "parent_id" not in payload:
                missing_parent_id += 1

            # Noisy check — heuristic re-computation
            noisy, reason = is_noisy_chunk(text, header)
            if noisy:
                noisy_count += 1
                preview = text[:80].replace("\n", " ").strip()
                noisy_details.append(f"  [id={point.id}] ({reason}) → \"{preview}…\"")

            # Also count payload-tagged noisy (Step 6.5 ingestion)
            if payload.get("is_noisy", False):
                payload_noisy_count += 1

        # ── Print distributions ─────────────────────────────────────
        def print_counter(name: str, counter: Counter, max_items: int = 30) -> None:
            print(f"\n{'─' * 60}")
            print(f"  {name} ({sum(counter.values())} tags across {len(counter)} values)")
            print(f"{'─' * 60}")
            for val, cnt in counter.most_common(max_items):
                print(f"    {val:40s}: {cnt}")

        print_counter("domain_topic", domain_topic_ctr)
        print_counter("content_type", content_type_ctr)
        print_counter("concern", concern_ctr)
        print_counter("ingredient", ingredient_ctr)
        print_counter("safety_context", safety_context_ctr)
        print_counter("skin_type", skin_type_ctr)
        print_counter("body_area", body_area_ctr)
        print_counter("header", header_ctr)

        # ── Key ingredient/safety counts ────────────────────────────
        print(f"\n{'═' * 60}")
        print("  KEY METADATA COUNTS")
        print(f"{'═' * 60}")
        print(f"  ingredient=benzoyl_peroxide : {ingredient_ctr.get('benzoyl_peroxide', 0)}")
        print(f"  ingredient=retinoid         : {ingredient_ctr.get('retinoid', 0)}")
        print(f"  safety_context=dryness      : {safety_context_ctr.get('dryness', 0)}")
        print(f"  safety_context=irritation   : {safety_context_ctr.get('irritation', 0)}")
        print(f"  content_type=side_effect    : {content_type_ctr.get('side_effect', 0)}")
        print(f"  content_type=treatment      : {content_type_ctr.get('treatment', 0)}")

        # ── Quality summary ─────────────────────────────────────────
        print(f"\n{'═' * 60}")
        print("  QUALITY SUMMARY")
        print(f"{'═' * 60}")
        print(f"  Total points               : {len(all_points)}")
        print(f"  metadata_confidence = 0     : {zero_confidence}")
        print(f"  Missing domain_topic        : {missing_domain_topic}")
        print(f"  Missing content_type        : {missing_content_type}")
        print(f"  Missing parent_id           : {missing_parent_id}")
        print(f"  Noisy chunks (heuristic)    : {noisy_count}")
        print(f"  Noisy chunks (payload tag)  : {payload_noisy_count}")

        if noisy_details:
            print(f"\n  Noisy chunk details (first 20):")
            for detail in noisy_details[:20]:
                print(detail)

        # ── Coverage assessment ─────────────────────────────────────
        print(f"\n{'═' * 60}")
        print("  COVERAGE ASSESSMENT")
        print(f"{'═' * 60}")

        if ingredient_ctr.get("benzoyl_peroxide", 0) == 0:
            print("  ⚠️  benzoyl_peroxide: NOT FOUND in any chunk.")
            print("     → 30-chunk sample likely doesn't cover treatment sections.")
            print("     → Recommend: --limit-files 1 (full file ingestion)")
        else:
            print(f"  ✅ benzoyl_peroxide found in {ingredient_ctr['benzoyl_peroxide']} chunk(s)")

        if ingredient_ctr.get("retinoid", 0) == 0:
            print("  ⚠️  retinoid: NOT FOUND in any chunk.")
        else:
            print(f"  ✅ retinoid found in {ingredient_ctr['retinoid']} chunk(s)")

        if safety_context_ctr.get("dryness", 0) == 0:
            print("  ⚠️  dryness: NOT FOUND in any chunk.")
        else:
            print(f"  ✅ dryness found in {safety_context_ctr['dryness']} chunk(s)")

        if safety_context_ctr.get("irritation", 0) == 0:
            print("  ⚠️  irritation: NOT FOUND in any chunk.")
        else:
            print(f"  ✅ irritation found in {safety_context_ctr['irritation']} chunk(s)")

        print(f"{'═' * 60}")
        return 0

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
        description="Analyze Qdrant v2 metadata distribution.",
    )
    parser.add_argument(
        "--collection",
        default=None,
        help="Collection name. Falls back to env QDRANT_COLLECTION_NAME, "
             "then QDRANT_COLLECTION, then 'acne_knowledge_v2'.",
    )
    args = parser.parse_args()

    collection, source = _resolve_collection(args.collection)

    print("=" * 60)
    print("  Phase 1.5 Step 5.5 – Metadata Distribution Analysis")
    print("=" * 60)
    print(f"  Collection from : {source}")
    print(f"  Using collection: {collection}")

    return asyncio.run(analyze(collection))


if __name__ == "__main__":
    raise SystemExit(main())
