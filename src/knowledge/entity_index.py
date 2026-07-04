"""Qdrant entity-card index helpers for the ``acne_entities_v1`` collection."""

from __future__ import annotations

import inspect
import os
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from src.database.vector_store import (
    QDRANT_COLLECTION_NAME,
    compute_sparse_vector,
    qdrant_client_kwargs,
)
from src.knowledge.entity_cards import entity_card_to_text
from src.knowledge.schemas import EntityCard
from src.knowledge.versioning import (
    get_embedding_metadata,
    get_knowledge_versions,
)


ENTITY_COLLECTION_DEFAULT = "acne_entities_v1"
CHUNK_COLLECTION_DEFAULT = os.getenv("QDRANT_COLLECTION_NAME", "acne_knowledge")
CHUNK_COLLECTION_FUTURE_DEFAULT = "acne_chunks_v1"

EmbeddingProvider = Callable[[list[str]], list[list[float]] | Awaitable[list[list[float]]]]


def get_entity_collection_name() -> str:
    return os.getenv("ENTITY_QDRANT_COLLECTION_NAME", ENTITY_COLLECTION_DEFAULT)


def get_chunk_collection_name() -> str:
    qdrant_collection = os.getenv("QDRANT_COLLECTION_NAME", CHUNK_COLLECTION_DEFAULT).strip()
    qdrant_collection = qdrant_collection or CHUNK_COLLECTION_DEFAULT
    configured = os.getenv("CHUNK_QDRANT_COLLECTION_NAME", "").strip()
    if not configured or configured == CHUNK_COLLECTION_FUTURE_DEFAULT:
        return qdrant_collection
    return configured


def entity_point_id(card: EntityCard, kb_version: str = "acne_kb_v1") -> str:
    """Return a deterministic Qdrant-compatible UUID for an entity card."""

    return str(uuid.uuid5(uuid.NAMESPACE_URL, card.stable_id(kb_version=kb_version)))


def build_entity_point_payload(card: EntityCard, kb_version: str = "acne_kb_v1") -> dict[str, Any]:
    """Build the Qdrant payload for an entity card."""

    payload = card.to_payload()
    payload.update(
        {
            "text": entity_card_to_text(card),
            "kb_version": kb_version,
            **get_embedding_metadata(),
            **get_knowledge_versions(),
            "entity_id": card.stable_id(kb_version=kb_version),
            "point_id": entity_point_id(card, kb_version=kb_version),
        }
    )
    payload["kb_version"] = kb_version
    return payload


async def ensure_entity_collection(
    client: Any | None = None,
    collection_name: str | None = None,
    *,
    recreate: bool = False,
    embedding_dimensions: int | None = None,
) -> None:
    """Create or validate the entity Qdrant collection.

    Existing collections are never deleted unless ``recreate=True`` and the
    target is not the configured chunk collection.
    """

    collection_name = collection_name or get_entity_collection_name()
    embedding_dimensions = embedding_dimensions or int(
        get_embedding_metadata()["embedding_dimensions"]
    )
    owns_client = client is None

    protected_collections = {
        "acne_knowledge",
        CHUNK_COLLECTION_FUTURE_DEFAULT,
        QDRANT_COLLECTION_NAME,
        get_chunk_collection_name(),
    }
    if recreate and collection_name in protected_collections:
        raise RuntimeError(
            "Refusing to recreate the configured chunk collection. "
            f"Target collection was {collection_name!r}."
        )

    if client is None:
        from qdrant_client import AsyncQdrantClient  # type: ignore[import]

        client = AsyncQdrantClient(**qdrant_client_kwargs())

    try:
        from qdrant_client.models import Distance, SparseVectorParams, VectorParams  # type: ignore[import]

        collections = await client.get_collections()
        existing_names = {collection.name for collection in collections.collections}

        if collection_name in existing_names and recreate:
            await client.delete_collection(collection_name=collection_name)
            existing_names.remove(collection_name)

        if collection_name not in existing_names:
            await client.create_collection(
                collection_name=collection_name,
                vectors_config={
                    "dense": VectorParams(
                        size=embedding_dimensions,
                        distance=Distance.COSINE,
                    )
                },
                sparse_vectors_config={"bm25": SparseVectorParams()},
            )
            return

        info = await client.get_collection(collection_name=collection_name)
        _validate_entity_collection_schema(
            params=info.config.params,
            collection_name=collection_name,
            embedding_dimensions=embedding_dimensions,
        )
    finally:
        if owns_client:
            await client.close()


def build_entity_point(
    card: EntityCard,
    dense_vector: list[float],
    kb_version: str = "acne_kb_v1",
) -> Any:
    """Build a Qdrant ``PointStruct`` with dense and hashed sparse BM25 vectors."""

    from qdrant_client.models import PointStruct, SparseVector  # type: ignore[import]

    payload = build_entity_point_payload(card, kb_version=kb_version)
    sparse = compute_sparse_vector(payload["text"])
    vector: dict[str, Any] = {"dense": dense_vector}
    if sparse["indices"]:
        vector["bm25"] = SparseVector(indices=sparse["indices"], values=sparse["values"])

    return PointStruct(
        id=payload["point_id"],
        vector=vector,
        payload=payload,
    )


async def upsert_entity_cards(
    cards: list[EntityCard],
    embeddings: list[list[float]] | None = None,
    *,
    embedding_provider: EmbeddingProvider | None = None,
    client: Any | None = None,
    collection_name: str | None = None,
    kb_version: str = "acne_kb_v1",
    batch_size: int = 64,
) -> int:
    """Upsert entity cards into Qdrant using precomputed embeddings or a provider."""

    if embeddings is None:
        if embedding_provider is None:
            raise ValueError("Provide either embeddings or embedding_provider.")
        texts = [entity_card_to_text(card) for card in cards]
        maybe_embeddings = embedding_provider(texts)
        embeddings = await maybe_embeddings if inspect.isawaitable(maybe_embeddings) else maybe_embeddings

    if len(embeddings) != len(cards):
        raise ValueError(
            f"Embedding count mismatch: got {len(embeddings)}, expected {len(cards)}."
        )

    for index, vector in enumerate(embeddings):
        expected_dimensions = int(get_embedding_metadata()["embedding_dimensions"])
        if len(vector) != expected_dimensions:
            raise ValueError(
                f"Embedding dimension mismatch at card {index}: got {len(vector)}, "
                f"expected {expected_dimensions}."
            )

    collection_name = collection_name or get_entity_collection_name()
    owns_client = client is None
    if client is None:
        from qdrant_client import AsyncQdrantClient  # type: ignore[import]

        client = AsyncQdrantClient(**qdrant_client_kwargs())

    try:
        total = 0
        for start in range(0, len(cards), batch_size):
            batch_cards = cards[start:start + batch_size]
            batch_embeddings = embeddings[start:start + batch_size]
            points = [
                build_entity_point(card, dense_vector, kb_version=kb_version)
                for card, dense_vector in zip(batch_cards, batch_embeddings)
            ]
            await client.upsert(collection_name=collection_name, points=points)
            total += len(points)
        return total
    finally:
        if owns_client:
            await client.close()


def _validate_entity_collection_schema(
    params: Any,
    collection_name: str,
    embedding_dimensions: int,
) -> None:
    if isinstance(params, dict):
        vectors_config = params.get("vectors")
        sparse_vectors_config = params.get("sparse_vectors")
    else:
        vectors_config = getattr(params, "vectors", None)
        sparse_vectors_config = getattr(params, "sparse_vectors", None)

    dense_config = _get_named_config(vectors_config, "dense")
    bm25_config = _get_named_config(sparse_vectors_config, "bm25")
    schema_errors: list[str] = []

    if dense_config is None:
        schema_errors.append("missing named dense vector 'dense'")
    else:
        dense_size = (
            dense_config.get("size")
            if isinstance(dense_config, dict)
            else getattr(dense_config, "size", None)
        )
        if dense_size != embedding_dimensions:
            schema_errors.append(
                f"named vector 'dense' has size {dense_size}, expected {embedding_dimensions}"
            )

    if bm25_config is None:
        schema_errors.append("missing sparse vector 'bm25'")

    if schema_errors:
        raise RuntimeError(
            f"Qdrant entity collection schema mismatch for {collection_name!r}: "
            + "; ".join(schema_errors)
            + ". Do not delete chunk collections; create/migrate the entity collection manually "
            "or rerun the entity index script with a safe entity-only target."
        )


def _get_named_config(config: Any, name: str) -> Any:
    if config is None:
        return None
    if isinstance(config, dict):
        return config.get(name)
    if hasattr(config, "get"):
        return config.get(name)
    return None


__all__ = [
    "ENTITY_COLLECTION_DEFAULT",
    "build_entity_point",
    "build_entity_point_payload",
    "ensure_entity_collection",
    "entity_point_id",
    "get_chunk_collection_name",
    "get_entity_collection_name",
    "upsert_entity_cards",
]
