#!/usr/bin/env python3
"""
inspect_dermatology_chunks.py
=============================
Phase 1.5 – Inspect chunks with dermatology metadata.

Uses simulated Markdown (no LlamaParse, no Qdrant, no Neo4j).
Calls chunk_markdown_text() from ingest_knowledge.py to verify that
dermatology metadata is correctly attached to each SemanticChunk.

Usage
-----
    python scripts/diagnostics/inspect_dermatology_chunks.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Bootstrap
# ─────────────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.ingest_knowledge import chunk_markdown_text

# ─────────────────────────────────────────────────────────────────────────────
# Simulated Markdown content
# ─────────────────────────────────────────────────────────────────────────────

SIMULATED_MARKDOWN = """\
# Acne

## Causes
Mụn trứng cá có thể liên quan đến tăng tiết bã nhờn, bít tắc nang lông và vi khuẩn C. acnes.

## Treatment
Benzoyl peroxide và retinoid thường được nhắc đến trong điều trị mụn viêm.

## Side Effects
Benzoyl peroxide có thể gây khô da, kích ứng, bong tróc hoặc nóng rát.

## Special Population
Phụ nữ mang thai hoặc trẻ em cần thận trọng khi dùng thuốc trị mụn.
"""

# ─────────────────────────────────────────────────────────────────────────────
# Metadata fields to display
# ─────────────────────────────────────────────────────────────────────────────

DISPLAY_FIELDS = [
    "domain_topic",
    "content_type",
    "concern",
    "ingredient",
    "skin_type",
    "body_area",
    "safety_context",
    "metadata_confidence",
    "metadata_extraction_method",
    # Hierarchical parent-child fields (Step 3)
    "parent_id",
    "chunk_level",
    "parent_header_path",
    "child_index_in_parent",
    "parent_text_hash",
    "section_char_length",
]

# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    print("=" * 70)
    print("  Phase 1.5 – Inspect Dermatology Chunks")
    print("=" * 70)

    chunks = chunk_markdown_text(
        markdown_text=SIMULATED_MARKDOWN,
        source_file="simulated_acne_doc.pdf",
        max_section_chars=2000,
    )

    print(f"\n  Total chunks produced: {len(chunks)}\n")

    limit = min(10, len(chunks))
    has_error = False

    for i, chunk in enumerate(chunks[:limit]):
        print("─" * 70)
        print(f"  Chunk {i}")
        print("─" * 70)

        print(f"  chunk_index  : {chunk.chunk_index}")
        print(f"  header_path  : {chunk.header_path!r}")

        # Text preview (first 120 chars)
        preview = chunk.text[:120].replace("\n", " ")
        if len(chunk.text) > 120:
            preview += "…"
        print(f"  text         : {preview}")

        meta = chunk.metadata

        for field in DISPLAY_FIELDS:
            value = meta.get(field)
            if isinstance(value, list):
                display = ", ".join(value) if value else "—"
            elif value is None:
                display = "—"
            else:
                display = str(value)
            print(f"  {field:30s}: {display}")

        # Validation: every chunk must have extraction_method
        if meta.get("metadata_extraction_method") != "rule_based":
            print("  ⚠️  WARNING: metadata_extraction_method is not 'rule_based'!")
            has_error = True

        print()

    # ── Summary ────────────────────────────────────────────────────────
    print("=" * 70)
    print("  Qdrant Payload Preview (chunk 0)")
    print("=" * 70)

    if chunks:
        first = chunks[0]
        payload = {
            **first.metadata,
            "chunk_id": first.chunk_id,
            "text": first.text[:200] + "…" if len(first.text) > 200 else first.text,
            "header": first.header_path,
            "graph_nodes": [],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))

    print()
    print("=" * 70)

    # Basic sanity checks
    all_ok = True

    required_fields = [
        # Dermatology metadata (Step 2)
        "domain_topic", "metadata_confidence", "metadata_extraction_method",
        # Hierarchical metadata (Step 3)
        "parent_id", "chunk_level", "parent_header_path",
        "child_index_in_parent", "parent_text_hash", "section_char_length",
    ]

    for chunk in chunks:
        m = chunk.metadata
        for field in required_fields:
            if field not in m:
                print(f"  ❌ Chunk {chunk.chunk_index}: missing {field}")
                all_ok = False

    if all_ok and not has_error:
        print("  ✅ All chunks have dermatology + hierarchical metadata fields.")
    else:
        print("  ❌ Some chunks are missing expected metadata fields.")

    print("=" * 70)
    return 0 if (all_ok and not has_error) else 1


if __name__ == "__main__":
    raise SystemExit(main())
