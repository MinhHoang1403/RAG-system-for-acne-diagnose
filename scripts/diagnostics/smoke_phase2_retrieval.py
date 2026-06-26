#!/usr/bin/env python3
"""
Smoke test Phase 2 retrieval without running ingestion.

Checks:
- Qdrant dense + sparse retrieval through HybridRetriever
- Neo4j keyword/entity lookup
- Basic payload/schema expectations from Phase 1
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env", override=False)
except ImportError:
    pass

from src.api.preflight import run_phase2_preflight
from src.database.graph_store import Neo4jGraphStore
from src.database.retriever import HybridRetriever


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("test_phase2_retrieval")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


async def main() -> int:
    query = "acne vulgaris treatment"

    logger.info("Running Phase 2 preflight...")
    preflight = await run_phase2_preflight()
    logger.info("Preflight status: %s", preflight["status"])
    for name, check in preflight["checks"].items():
        logger.info("  %s: %s", name, check)

    _require(preflight["checks"]["qdrant"]["status"] == "ok", "Qdrant preflight failed")
    _require(preflight["checks"]["neo4j"]["status"] == "ok", "Neo4j preflight failed")
    _require(preflight["checks"]["ollama"]["status"] == "ok", "Ollama preflight failed")

    retriever = HybridRetriever()
    try:
        logger.info("Testing hybrid retrieval for query: %s", query)
        result = await retriever.retrieve(query, top_k=5)
    finally:
        await retriever.close()

    logger.info("Hybrid metadata: %s", result.metadata)
    logger.info("Sources: %s", result.sources)
    logger.info("Vector contexts: %d", len(result.vector_contexts))
    logger.info("Graph facts: %d", len(result.graph_facts))

    _require(result.vector_contexts, "Hybrid retrieval returned no vector contexts")
    _require(result.sources, "Hybrid retrieval returned no sources")

    first = result.vector_contexts[0]
    _require("text" in first and first["text"], "Qdrant payload missing text")
    _require("chunk_id" in first and first["chunk_id"], "Qdrant payload missing chunk_id")
    _require("source_file" in first and first["source_file"], "Qdrant payload missing source_file")

    graph = Neo4jGraphStore()
    try:
        logger.info("Testing Neo4j keyword search...")
        keyword_facts = await graph.search_by_keywords(["acne"], limit=10)
        if not keyword_facts:
            logger.info("Keyword search returned no facts, trying direct entity context.")
            keyword_facts = await graph.get_entity_context(["acne vulgaris"], limit=10)
    finally:
        await graph.close()

    logger.info("Neo4j facts: %d", len(keyword_facts))
    _require(keyword_facts, "Neo4j returned no acne-related facts")

    print("PHASE2_RETRIEVAL_OK")
    print(f"vector_contexts={len(result.vector_contexts)}")
    print(f"graph_facts={len(result.graph_facts)}")
    print(f"sources={result.sources}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except AssertionError as exc:
        logger.error("Phase 2 retrieval test failed: %s", exc)
        raise SystemExit(1)
