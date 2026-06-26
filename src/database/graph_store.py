"""
src/database/graph_store.py – Neo4j Knowledge Graph Store
=========================================================
Read-only async client for querying the Neo4j knowledge graph
populated during Pha 1 ingestion.

Schema (from ingest_knowledge.py)
---------------------------------
Node labels : DISEASE, DRUG, SYMPTOM, TREATMENT, MECHANISM, BODY_PART
Node props  : name (unique, lowercase), description, created_at
Relationships : CAUSES, TREATS, CONTRAINDICATES, PART_OF
Rel props   : evidence, created_at
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (from .env)
# ---------------------------------------------------------------------------
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")


class Neo4jGraphStore:
    """Async read-only client for the acne knowledge graph in Neo4j.

    Usage
    -----
    store = Neo4jGraphStore()
    facts = await store.get_entity_context(["isotretinoin", "acne vulgaris"])
    await store.close()
    """

    def __init__(self) -> None:
        from neo4j import AsyncGraphDatabase  # type: ignore[import]

        self._driver = AsyncGraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USERNAME, NEO4J_PASSWORD),
        )
        logger.debug("Neo4j driver created for %s", NEO4J_URI)

    async def get_entity_context(
        self,
        entity_names: list[str],
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get 1-hop relationships for given entity names.

        Parameters
        ----------
        entity_names : list[str]
            Entity names to look up (will be lowercased to match ingestion).
        limit : int
            Maximum number of fact records to return.

        Returns
        -------
        list[dict]
            Each dict contains: entity, entity_type, description,
            relationship, related_entity, related_type,
            related_description, evidence.
        """
        if not entity_names:
            return []

        # Normalise to lowercase (matching Pha 1 ingestion format)
        names = list({n.strip().lower() for n in entity_names if n.strip()})

        if not names:
            return []

        # Undirected 1-hop traversal: (n)-[r]-(m) matches both directions
        cypher = """
        MATCH (n)
        WHERE n.name IN $names
        OPTIONAL MATCH (n)-[r]-(m)
        RETURN n.name            AS entity,
               labels(n)[0]      AS entity_type,
               n.description     AS description,
               type(r)           AS relationship,
               m.name            AS related_entity,
               labels(m)[0]      AS related_type,
               m.description     AS related_description,
               r.evidence        AS evidence
        LIMIT $limit
        """

        facts: list[dict[str, Any]] = []

        try:
            async with self._driver.session() as session:
                result = await session.run(cypher, names=names, limit=limit)
                records = [record async for record in result]

                seen_entities: set[str] = set()
                for record in records:
                    fact = dict(record)
                    rel = fact.get("relationship")
                    entity = fact.get("entity", "")

                    if rel is not None:
                        # Has a relationship – include it
                        facts.append(fact)
                        seen_entities.add(entity)
                    elif entity not in seen_entities:
                        # Entity without relationships (isolated node)
                        facts.append(fact)
                        seen_entities.add(entity)

        except Exception as exc:
            logger.error("Neo4j get_entity_context failed: %s", exc)

        logger.debug(
            "Neo4j: queried %d entity names → %d facts",
            len(names),
            len(facts),
        )

        return facts

    async def search_by_keywords(
        self,
        keywords: list[str],
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        """Fallback: search entities whose name contains any keyword.

        Used when ``graph_nodes`` from Qdrant payload are empty.

        Parameters
        ----------
        keywords : list[str]
            Keywords to search (min 3 chars each, lowercased).
        limit : int
            Maximum number of fact records to return.
        """
        if not keywords:
            return []

        # Filter out very short keywords that would match too broadly
        keywords = [kw.strip().lower() for kw in keywords if len(kw.strip()) >= 3]

        if not keywords:
            return []

        cypher = """
        MATCH (n)
        WHERE ANY(kw IN $keywords WHERE n.name CONTAINS kw)
        OPTIONAL MATCH (n)-[r]-(m)
        RETURN n.name            AS entity,
               labels(n)[0]      AS entity_type,
               n.description     AS description,
               type(r)           AS relationship,
               m.name            AS related_entity,
               labels(m)[0]      AS related_type,
               m.description     AS related_description,
               r.evidence        AS evidence
        LIMIT $limit
        """

        facts: list[dict[str, Any]] = []

        try:
            async with self._driver.session() as session:
                result = await session.run(
                    cypher,
                    keywords=keywords,
                    limit=limit,
                )
                records = [record async for record in result]

                for record in records:
                    facts.append(dict(record))

        except Exception as exc:
            logger.error("Neo4j keyword search failed: %s", exc)

        logger.debug(
            "Neo4j: keyword search %s → %d facts",
            keywords[:5],
            len(facts),
        )

        return facts

    async def close(self) -> None:
        """Close the Neo4j driver."""
        await self._driver.close()
        logger.debug("Neo4j driver closed.")
