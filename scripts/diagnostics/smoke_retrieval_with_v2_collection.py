#!/usr/bin/env python3
"""
test_retrieval_with_v2_collection.py
=====================================
Phase 1.5 Step 5.5 – Enhanced retrieval test with diagnostics.

Performs Qdrant-only semantic search (dense + sparse) with RRF fusion
and metadata boost.  Does NOT call Neo4j or LLM.

Enhancements vs v1:
- Prints query_metadata BEFORE searching
- Checks sparse vector presence in collection config
- Raw sparse vector diagnostics (index count, value range)
- Shows top-15 BEFORE boost and AFTER boost
- Better matched_metadata_fields display

Requires:
- Running Qdrant at http://localhost:6333
- Collection ``acne_knowledge_v2`` with indexed vectors
- GOOGLE_API_KEY set in .env for Gemini embedding

Usage
-----
    python scripts/diagnostics/smoke_retrieval_with_v2_collection.py
    python scripts/diagnostics/smoke_retrieval_with_v2_collection.py --collection acne_knowledge_v2
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
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
# Imports (after bootstrap so env is loaded)
# ─────────────────────────────────────────────────────────────────────────────

from src.database.retriever import (
    apply_metadata_boost,
    extract_query_dermatology_metadata,
)
from src.database.vector_store import (
    QdrantVectorStore,
    compute_sparse_vector,
    embed_query,
)


# ─────────────────────────────────────────────────────────────────────────────
# Test queries
# ─────────────────────────────────────────────────────────────────────────────

TEST_QUERIES = [
    "Da dầu bị mụn nên dùng gì?",
    "Retinoid có gây kích ứng không?",
    "Benzoyl peroxide có thể gây khô da không?",
]


# ─────────────────────────────────────────────────────────────────────────────
# Lightweight RRF (avoids instantiating full HybridRetriever / Neo4j)
# ─────────────────────────────────────────────────────────────────────────────

def _rrf_fusion(
    dense_results: list[dict],
    sparse_results: list[dict],
    k: int = 60,
) -> list[dict]:
    doc_scores: dict[str, float] = {}
    doc_data: dict[str, dict] = {}

    for rank, doc in enumerate(dense_results, start=1):
        doc_id = str(doc.get("id", ""))
        if not doc_id:
            continue
        doc_scores[doc_id] = doc_scores.get(doc_id, 0.0) + 1.0 / (k + rank)
        if doc_id not in doc_data:
            doc_data[doc_id] = doc.copy()

    for rank, doc in enumerate(sparse_results, start=1):
        doc_id = str(doc.get("id", ""))
        if not doc_id:
            continue
        doc_scores[doc_id] = doc_scores.get(doc_id, 0.0) + 1.0 / (k + rank)
        if doc_id not in doc_data:
            doc_data[doc_id] = doc.copy()

    ranked_ids = sorted(doc_scores, key=lambda d: doc_scores[d], reverse=True)

    result: list[dict] = []
    for doc_id in ranked_ids:
        doc = doc_data[doc_id]
        doc["rrf_score"] = round(doc_scores[doc_id], 6)
        doc["score"] = doc["rrf_score"]
        result.append(doc)

    return result


def _print_result_row(
    idx: int,
    r: dict,
    show_boost: bool = True,
) -> None:
    """Print a single result row compactly."""
    text_preview = r.get("text", "")[:120].replace("\n", " ")
    score_field = "boosted_score" if show_boost else "score"
    score = r.get(score_field, r.get("score", 0))

    boost_info = ""
    if show_boost:
        boost_val = r.get("metadata_boost", 0)
        matched = r.get("matched_metadata_fields", [])
        if boost_val > 0:
            boost_info = f"  boost=+{boost_val:.2f} matched={matched}"

    print(f"  [{idx:2d}] score={score:.4f}{boost_info}")
    print(f"       header={r.get('header', '?')}")
    print(f"       ingredient={r.get('ingredient', [])}"
          f"  concern={r.get('concern', [])}"
          f"  safety={r.get('safety_context', [])}")
    print(f"       text: {text_preview}…")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

async def run_test(collection: str) -> int:
    import src.database.vector_store as vs_module
    original_collection = vs_module.QDRANT_COLLECTION_NAME
    vs_module.QDRANT_COLLECTION_NAME = collection

    print(f"  Using collection: {collection}")
    print(f"  Qdrant URL:       {vs_module.QDRANT_URL}")
    print()

    store = QdrantVectorStore()
    store._collection = collection

    all_ok = True

    try:
        # ── Verify collection + check sparse config ──────────────────
        from qdrant_client import AsyncQdrantClient  # type: ignore
        check_client = AsyncQdrantClient(**vs_module.qdrant_client_kwargs())

        try:
            collections_resp = await check_client.get_collections()
            existing = {c.name for c in collections_resp.collections}
            if collection not in existing:
                print(f"  ❌ Collection '{collection}' not found.")
                print(f"     Available: {sorted(existing)}")
                return 1

            info = await check_client.get_collection(collection_name=collection)
            print(f"  ✅ Collection '{collection}' exists.")
            print(f"  Points: {info.points_count}")

            # Check sparse vector config
            sparse_config = info.config.params.sparse_vectors or {}
            print(f"  Sparse vectors config: {list(sparse_config.keys()) if sparse_config else 'NONE ❌'}")
            if not sparse_config:
                print("  ⚠️  No sparse vectors configured! BM25 search will return 0.")
                print("  → Collection may have been created without sparse_vectors_config.")
            elif "bm25" not in sparse_config:
                print(f"  ⚠️  'bm25' not in sparse config. Available: {list(sparse_config.keys())}")
            else:
                print("  ✅ 'bm25' sparse vector present in collection config.")

            # Check if points actually have sparse vectors stored
            scroll_check = await check_client.scroll(
                collection_name=collection,
                limit=1,
                with_payload=False,
                with_vectors=True,
            )
            if scroll_check[0]:
                pt = scroll_check[0][0]
                vectors = pt.vector
                if isinstance(vectors, dict):
                    has_bm25 = "bm25" in vectors
                    print(f"  Sample point vector keys: {list(vectors.keys())}")
                    if has_bm25:
                        bm25_vec = vectors["bm25"]
                        if hasattr(bm25_vec, "indices"):
                            print(f"  ✅ bm25 vector stored: {len(bm25_vec.indices)} indices")
                        else:
                            print(f"  ✅ bm25 vector present (type={type(bm25_vec).__name__})")
                    else:
                        print("  ❌ bm25 vector NOT stored in points!")
                        print("  → Sparse search will return 0 results.")
                else:
                    print(f"  ⚠️  Unexpected vector format: {type(vectors)}")

            print()

        finally:
            await check_client.close()

        # ── Run queries ──────────────────────────────────────────────
        for qi, query in enumerate(TEST_QUERIES, start=1):
            print("═" * 72)
            print(f"  Query {qi}: {query}")
            print("═" * 72)

            # ── Query metadata extraction ────────────────────────────
            query_meta = extract_query_dermatology_metadata(query)
            print(f"\n  📋 Query Metadata:")
            for field in ["ingredient", "concern", "content_type", "domain_topic",
                          "skin_type", "safety_context", "body_area"]:
                vals = query_meta.get(field, [])
                if vals:
                    print(f"    {field:20s}: {vals}")
            print()

            # ── Embed ────────────────────────────────────────────────
            try:
                query_vector = await embed_query(query)
                print(f"  ✅ Embedded (dim={len(query_vector)})")
            except Exception as exc:
                print(f"  ❌ Embedding failed: {exc}")
                all_ok = False
                continue

            # ── Dense search ─────────────────────────────────────────
            fetch_k = 15
            try:
                dense_results = await store.search(
                    query_vector=query_vector,
                    top_k=fetch_k,
                )
                print(f"  Dense results: {len(dense_results)}")
            except Exception as exc:
                print(f"  ❌ Dense search failed: {exc}")
                all_ok = False
                continue

            # ── Sparse search + diagnostics ──────────────────────────
            try:
                # Show raw sparse vector stats
                sparse_vec = compute_sparse_vector(query)
                print(f"  Sparse query vector: {len(sparse_vec['indices'])} indices, "
                      f"value range [{min(sparse_vec['values']):.3f}, {max(sparse_vec['values']):.3f}]"
                      if sparse_vec['indices'] else "  Sparse query vector: EMPTY")

                sparse_results = await store.search_sparse(
                    text=query,
                    top_k=fetch_k,
                )
                print(f"  Sparse results: {len(sparse_results)}")
                if len(sparse_results) == 0:
                    print("  ⚠️  Sparse returned 0 — see sparse vector diagnostics above")
            except Exception as exc:
                print(f"  ❌ Sparse search failed: {exc}")
                sparse_results = []

            # ── RRF fusion ───────────────────────────────────────────
            fused = _rrf_fusion(dense_results, sparse_results)
            print(f"  Fused results: {len(fused)}")

            # ── Show top-15 BEFORE boost ─────────────────────────────
            top_k = 5
            print(f"\n  ── Top-{min(15, len(fused))} BEFORE metadata boost ──")
            for ri, r in enumerate(fused[:15]):
                _print_result_row(ri, r, show_boost=False)

            # ── Apply metadata boost ─────────────────────────────────
            boosted = apply_metadata_boost(fused, query_meta)
            top = boosted[:top_k]

            boost_count = sum(1 for r in boosted if r.get("metadata_boost_applied"))

            print(f"\n  ── Top-{top_k} AFTER metadata boost "
                  f"({boost_count}/{len(boosted)} boosted) ──")
            for ri, r in enumerate(top):
                _print_result_row(ri, r, show_boost=True)

            # ── Validate ─────────────────────────────────────────────
            if len(top) == 0:
                print(f"  ❌ No results for query {qi}")
                all_ok = False

            print()

        return 0 if all_ok else 1

    finally:
        await store.close()
        vs_module.QDRANT_COLLECTION_NAME = original_collection


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
        description="Test retrieval with metadata boost on v2 collection.",
    )
    parser.add_argument(
        "--collection",
        default=None,
        help="Qdrant collection. Falls back to env QDRANT_COLLECTION_NAME, "
             "then QDRANT_COLLECTION, then 'acne_knowledge_v2'.",
    )
    args = parser.parse_args()

    collection, source = _resolve_collection(args.collection)

    print("=" * 72)
    print("  Phase 1.5 Step 5.5 – Enhanced Retrieval Test with Diagnostics")
    print("=" * 72)
    print(f"  Collection from : {source}")
    print(f"  Using collection: {collection}")

    return asyncio.run(run_test(collection))


if __name__ == "__main__":
    raise SystemExit(main())
