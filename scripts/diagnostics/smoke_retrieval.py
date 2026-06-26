#!/usr/bin/env python3
"""
scripts/diagnostics/smoke_retrieval.py – Test Hybrid Retrieval Pipeline
==========================================================

Run::

    python scripts/diagnostics/smoke_retrieval.py

Tests the end-to-end retrieval pipeline against live Qdrant (403 vectors)
and Neo4j (1127 nodes, 961 relationships) without requiring LangGraph
or the API layer.

Prerequisites
-------------
- Docker services running: ``docker compose up -d``
- Pha 1 data already ingested (Qdrant + Neo4j populated)
- GOOGLE_API_KEY set in ``.env`` for Gemini embedding
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env", override=False)
except ImportError:
    pass

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("test_retrieval")


# ---------------------------------------------------------------------------
# Test queries
# ---------------------------------------------------------------------------
TEST_QUERIES = [
    "isotretinoin side effects",
    "acne vulgaris treatment",
    "mụn trứng cá",
    "benzoyl peroxide mechanism",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def print_separator(char: str = "=", width: int = 70) -> None:
    print(char * width)


def truncate(text: str, max_len: int = 120) -> str:
    text = text.replace("\n", " ").strip()
    if len(text) <= max_len:
        return text
    return text[:max_len] + "…"


# ---------------------------------------------------------------------------
# Connection tests
# ---------------------------------------------------------------------------

async def test_qdrant_connection() -> bool:
    """Test basic Qdrant connectivity and collection info."""
    print_separator()
    print("🔌 TEST: Qdrant Connection")
    print_separator()

    try:
        from qdrant_client import AsyncQdrantClient  # type: ignore[import]
    except ImportError:
        print("  ✗ qdrant-client not installed.")
        return False

    url = os.getenv("QDRANT_URL", "http://localhost:6333")
    collection = os.getenv("QDRANT_COLLECTION_NAME", "acne_knowledge")

    client = AsyncQdrantClient(url=url)
    try:
        info = await client.get_collection(collection_name=collection)
        print(f"  ✓ Collection : {collection}")
        print(f"  ✓ Points     : {info.points_count}")
        print(f"  ✓ Vectors    : {info.config.params.vectors}")
        print(f"  ✓ Status     : {info.status}")
        return True
    except Exception as exc:
        print(f"  ✗ Qdrant connection failed: {exc}")
        return False
    finally:
        await client.close()


async def test_neo4j_connection() -> bool:
    """Test basic Neo4j connectivity and graph stats."""
    print_separator()
    print("🔌 TEST: Neo4j Connection")
    print_separator()

    try:
        from src.database.graph_store import Neo4jGraphStore
    except ImportError as exc:
        print(f"  ✗ Import error: {exc}")
        return False

    store = Neo4jGraphStore()
    try:
        async with store._driver.session() as session:
            result = await session.run(
                "MATCH (n) RETURN count(n) AS node_count"
            )
            record = await result.single()
            node_count = record["node_count"] if record else 0

            result2 = await session.run(
                "MATCH ()-[r]->() RETURN count(r) AS rel_count"
            )
            record2 = await result2.single()
            rel_count = record2["rel_count"] if record2 else 0

            # Get label distribution
            result3 = await session.run(
                "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS cnt "
                "ORDER BY cnt DESC"
            )
            labels = [
                f"{r['label']}={r['cnt']}"
                async for r in result3
            ]

            print(f"  ✓ Neo4j connected")
            print(f"  ✓ Nodes          : {node_count}")
            print(f"  ✓ Relationships  : {rel_count}")
            print(f"  ✓ Labels         : {', '.join(labels)}")
            return True
    except Exception as exc:
        print(f"  ✗ Neo4j connection failed: {exc}")
        return False
    finally:
        await store.close()


async def test_embedding() -> bool:
    """Test Gemini embedding for a sample query."""
    print_separator()
    print("🧬 TEST: Gemini Embedding")
    print_separator()

    try:
        from src.database.vector_store import embed_query
    except ImportError as exc:
        print(f"  ✗ Import error: {exc}")
        return False

    try:
        t0 = time.time()
        vec = await embed_query("test query for acne treatment")
        elapsed = time.time() - t0

        expected_dim = int(os.getenv("EMBEDDING_DIMENSIONS", "3072"))

        print(f"  ✓ Dimension      : {len(vec)} (expected {expected_dim})")
        print(f"  ✓ Time           : {elapsed:.2f}s")
        print(f"  ✓ First 5 values : [{', '.join(f'{v:.6f}' for v in vec[:5])}]")

        if len(vec) != expected_dim:
            print(f"  ⚠ Dimension mismatch! Got {len(vec)}, expected {expected_dim}")
            return False

        return True
    except Exception as exc:
        print(f"  ✗ Embedding failed: {exc}")
        return False


async def test_sparse_vector() -> bool:
    """Test sparse vector computation matches ingestion format."""
    print_separator()
    print("🔢 TEST: Sparse BM25 Vector")
    print_separator()

    try:
        from src.database.vector_store import compute_sparse_vector
    except ImportError as exc:
        print(f"  ✗ Import error: {exc}")
        return False

    try:
        test_text = "isotretinoin treats severe acne vulgaris"
        sparse = compute_sparse_vector(test_text)
        n_indices = len(sparse["indices"])
        n_values = len(sparse["values"])

        print(f"  ✓ Input text     : \"{test_text}\"")
        print(f"  ✓ Sparse indices : {n_indices}")
        print(f"  ✓ Sparse values  : {n_values}")
        print(f"  ✓ Sample indices : {sparse['indices'][:5]}")
        print(f"  ✓ Sample values  : {[round(v, 4) for v in sparse['values'][:5]]}")

        assert n_indices == n_values, "Indices and values length mismatch!"
        assert n_indices > 0, "Sparse vector is empty!"

        return True
    except Exception as exc:
        print(f"  ✗ Sparse vector failed: {exc}")
        return False


# ---------------------------------------------------------------------------
# Full pipeline test
# ---------------------------------------------------------------------------

async def test_hybrid_retrieval() -> None:
    """Test the full hybrid retrieval pipeline with multiple queries."""
    from src.database.retriever import HybridRetriever

    retriever = HybridRetriever()

    try:
        for query in TEST_QUERIES:
            print_separator()
            print(f"🔍 QUERY: \"{query}\"")
            print_separator()

            try:
                t0 = time.time()
                result = await retriever.retrieve(query, top_k=5)
                elapsed = time.time() - t0

                # ── Timing ───────────────────────────────────────────
                meta = result.metadata
                print(f"\n  ⏱  Total: {elapsed:.2f}s")
                print(
                    f"     Embed: {meta.get('embed_time_s', 0):.2f}s | "
                    f"Dense: {meta.get('dense_time_s', 0):.2f}s | "
                    f"Sparse: {meta.get('sparse_time_s', 0):.2f}s | "
                    f"Neo4j: {meta.get('neo4j_time_s', 0):.2f}s"
                )
                print(
                    f"     Counts — "
                    f"Dense: {meta.get('dense_count', 0)} | "
                    f"Sparse: {meta.get('sparse_count', 0)} | "
                    f"Fused: {meta.get('fused_count', 0)} | "
                    f"Entities: {meta.get('entity_names_count', 0)} | "
                    f"KG Facts: {meta.get('graph_facts_count', 0)}"
                )

                # ── Vector Contexts ──────────────────────────────────
                print(
                    f"\n  📄 Vector Contexts "
                    f"({len(result.vector_contexts)} chunks):"
                )
                for i, ctx in enumerate(result.vector_contexts, 1):
                    rrf = ctx.get("rrf_score", ctx.get("score", 0))
                    header = ctx.get("header", "N/A")
                    text_preview = truncate(ctx.get("text", ""), 100)
                    d_rank = ctx.get("dense_rank", "-")
                    s_rank = ctx.get("sparse_rank", "-")
                    g_nodes = ctx.get("graph_nodes", [])

                    print(
                        f"    {i}. [RRF={rrf:.4f}] "
                        f"(dense={d_rank}, sparse={s_rank})"
                    )
                    print(f"       Header : {header}")
                    print(f"       Text   : {text_preview}")
                    if g_nodes:
                        print(f"       KG     : {g_nodes[:5]}")

                # ── Graph Facts ──────────────────────────────────────
                print(
                    f"\n  🔗 Graph Facts "
                    f"({len(result.graph_facts)} facts):"
                )
                for i, fact in enumerate(result.graph_facts[:10], 1):
                    entity = fact.get("entity", "?")
                    etype = fact.get("entity_type", "?")
                    rel = fact.get("relationship")
                    related = fact.get("related_entity")
                    rtype = fact.get("related_type", "")

                    if rel and related:
                        print(
                            f"    {i}. ({etype}:{entity}) "
                            f"-[{rel}]-> "
                            f"({rtype}:{related})"
                        )
                    else:
                        desc = truncate(fact.get("description", "") or "", 60)
                        print(f"    {i}. ({etype}:{entity}) — {desc}")

                # ── Sources ──────────────────────────────────────────
                print(f"\n  📚 Sources: {result.sources}")
                print()

            except Exception as exc:
                print(f"\n  ✗ Retrieval failed for '{query}': {exc}")
                import traceback

                traceback.print_exc()
                print()

    finally:
        await retriever.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> int:
    print()
    print_separator("═")
    print("  Acne Advisor AI – Hybrid Retrieval Test Suite")
    print_separator("═")
    print()

    # ── 1. Connection tests ──────────────────────────────────────────
    qdrant_ok = await test_qdrant_connection()
    print()

    neo4j_ok = await test_neo4j_connection()
    print()

    if not qdrant_ok:
        print(
            "❌ Qdrant not available. "
            "Run: docker compose up -d qdrant"
        )
        return 1

    if not neo4j_ok:
        print(
            "❌ Neo4j not available. "
            "Run: docker compose up -d neo4j"
        )
        return 1

    # ── 2. Component tests ───────────────────────────────────────────
    sparse_ok = await test_sparse_vector()
    print()

    embed_ok = await test_embedding()
    print()

    if not embed_ok:
        print(
            "❌ Embedding failed. "
            "Check GOOGLE_API_KEY in .env"
        )
        return 1

    # ── 3. Full pipeline test ────────────────────────────────────────
    await test_hybrid_retrieval()

    print_separator("═")
    print("  ✅ All tests completed.")
    print_separator("═")
    print()

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
