#!/usr/bin/env python3
"""
test_hierarchical_chunking.py
=============================
Phase 1.5 Step 3 – Tests for hierarchical parent-child chunk metadata.

Uses simulated Markdown with a long Treatment section forced to split.
No LlamaParse, no Qdrant, no Neo4j.

Usage
-----
    python scripts/diagnostics/smoke_hierarchical_chunking.py
"""

from __future__ import annotations

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
# Simulated Markdown – Treatment is long enough to force splitting
# ─────────────────────────────────────────────────────────────────────────────

_TREATMENT_BLOCK = (
    "Benzoyl peroxide và retinoid thường được nhắc đến trong điều trị mụn viêm. "
    "Benzoyl peroxide có thể gây khô da, kích ứng, bong tróc hoặc nóng rát. "
    "Retinoid có thể gây kích ứng và bong tróc da. "
    "Salicylic acid thường được nhắc đến trong chăm sóc da dầu mụn. "
    "Azelaic acid có thể được nhắc đến trong một số tình huống mụn và thâm sau mụn."
)

# Repeat the treatment block to ensure it exceeds max_section_chars=200
SIMULATED_MARKDOWN = f"""\
# Acne

## Causes
Mụn trứng cá có thể liên quan đến tăng tiết bã nhờn, bít tắc nang lông và vi khuẩn C. acnes.

## Treatment
{_TREATMENT_BLOCK}

{_TREATMENT_BLOCK}

{_TREATMENT_BLOCK}
"""

# Use a small max to force split
MAX_SECTION_CHARS = 200

# ─────────────────────────────────────────────────────────────────────────────
# Test helpers
# ─────────────────────────────────────────────────────────────────────────────

PASS = "✅ PASS"
FAIL = "❌ FAIL"
all_ok = True


def assert_true(label: str, condition: bool) -> None:
    global all_ok
    status = PASS if condition else FAIL
    print(f"  {status}  {label}")
    if not condition:
        all_ok = False


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

def run_tests() -> bool:
    global all_ok

    chunks = chunk_markdown_text(
        markdown_text=SIMULATED_MARKDOWN,
        source_file="test_hierarchical.pdf",
        max_section_chars=MAX_SECTION_CHARS,
    )

    print(f"\n  Total chunks: {len(chunks)}  (max_section_chars={MAX_SECTION_CHARS})\n")

    # ── Identify Treatment chunks ──────────────────────────────────────
    treatment_chunks = [c for c in chunks if c.header_path == "Treatment"]
    causes_chunks = [c for c in chunks if c.header_path == "Causes"]

    print("─── Test 1: Treatment forced-split produces ≥2 chunks ───")
    assert_true(
        f"Treatment chunks = {len(treatment_chunks)} (≥ 2)",
        len(treatment_chunks) >= 2,
    )

    # ── Test 2: All Treatment chunks share parent_id ──────────────────
    print("\n─── Test 2: Treatment chunks share the same parent_id ───")
    treatment_parent_ids = {c.metadata["parent_id"] for c in treatment_chunks}
    assert_true(
        f"Unique parent_ids in Treatment = {len(treatment_parent_ids)} (should be 1)",
        len(treatment_parent_ids) == 1,
    )

    # ── Test 3: All Treatment chunks share parent_text_hash ───────────
    print("\n─── Test 3: Treatment chunks share the same parent_text_hash ───")
    treatment_hashes = {c.metadata["parent_text_hash"] for c in treatment_chunks}
    assert_true(
        f"Unique parent_text_hash in Treatment = {len(treatment_hashes)} (should be 1)",
        len(treatment_hashes) == 1,
    )

    # ── Test 4: child_index_in_parent is 0, 1, 2... no duplicates ─────
    print("\n─── Test 4: child_index_in_parent is sequential ───")
    child_indices = [c.metadata["child_index_in_parent"] for c in treatment_chunks]
    expected_indices = list(range(len(treatment_chunks)))
    assert_true(
        f"child_index_in_parent = {child_indices} (expected {expected_indices})",
        child_indices == expected_indices,
    )

    # ── Test 5: parent_header_path contains "Treatment" ───────────────
    print("\n─── Test 5: parent_header_path is 'Treatment' ───")
    for c in treatment_chunks:
        assert_true(
            f"Chunk {c.chunk_index} parent_header_path = {c.metadata['parent_header_path']!r}",
            "Treatment" in c.metadata["parent_header_path"],
        )

    # ── Test 6: section_char_length > 0 ───────────────────────────────
    print("\n─── Test 6: section_char_length > 0 for all chunks ───")
    for c in chunks:
        assert_true(
            f"Chunk {c.chunk_index} section_char_length = {c.metadata['section_char_length']}",
            c.metadata["section_char_length"] > 0,
        )

    # ── Test 7: Dermatology metadata still present ────────────────────
    print("\n─── Test 7: Dermatology metadata still present in Treatment chunks ───")
    all_ingredients = set()
    for c in treatment_chunks:
        all_ingredients.update(c.metadata.get("ingredient", []))
    assert_true(
        f"Treatment ingredients = {all_ingredients} (should contain benzoyl_peroxide or retinoid)",
        bool({"benzoyl_peroxide", "retinoid"} & all_ingredients),
    )

    # ── Test 8: No chunk missing parent_id ─────────────────────────────
    print("\n─── Test 8: No chunk missing parent_id ───")
    missing_parent = [c for c in chunks if "parent_id" not in c.metadata]
    assert_true(
        f"Chunks missing parent_id = {len(missing_parent)} (should be 0)",
        len(missing_parent) == 0,
    )

    # ── Test 9: All chunk_level == "child" ────────────────────────────
    print("\n─── Test 9: All chunks have chunk_level='child' ───")
    levels = {c.metadata.get("chunk_level") for c in chunks}
    assert_true(
        f"Unique chunk_level values = {levels} (should be {{'child'}})",
        levels == {"child"},
    )

    # ── Test 10: Causes section (unsplit) still has child_index=0 ─────
    print("\n─── Test 10: Unsplit Causes section has child_index_in_parent=0 ───")
    if causes_chunks:
        assert_true(
            f"Causes chunk child_index_in_parent = {causes_chunks[0].metadata['child_index_in_parent']}",
            causes_chunks[0].metadata["child_index_in_parent"] == 0,
        )
    else:
        assert_true("Causes section found", False)

    # ── Test 11: Different sections have different parent_ids ─────────
    print("\n─── Test 11: Causes and Treatment have different parent_ids ───")
    if causes_chunks and treatment_chunks:
        causes_pid = causes_chunks[0].metadata["parent_id"]
        treatment_pid = treatment_chunks[0].metadata["parent_id"]
        assert_true(
            f"Causes parent_id ({causes_pid}) != Treatment parent_id ({treatment_pid})",
            causes_pid != treatment_pid,
        )

    # ── Test 12: parent_id is stable across runs ─────────────────────
    print("\n─── Test 12: parent_id is deterministic (run twice, compare) ───")
    chunks2 = chunk_markdown_text(
        markdown_text=SIMULATED_MARKDOWN,
        source_file="test_hierarchical.pdf",
        max_section_chars=MAX_SECTION_CHARS,
    )
    pids_run1 = [c.metadata["parent_id"] for c in chunks]
    pids_run2 = [c.metadata["parent_id"] for c in chunks2]
    assert_true(
        f"parent_ids match across runs ({len(pids_run1)} ids)",
        pids_run1 == pids_run2,
    )

    return all_ok


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  Phase 1.5 Step 3 – Hierarchical Chunking Tests")
    print("=" * 60)

    success = run_tests()

    print("\n" + "=" * 60)
    if success:
        print("  ALL TESTS PASSED ✅")
    else:
        print("  SOME TESTS FAILED ❌")
    print("=" * 60)

    sys.exit(0 if success else 1)
