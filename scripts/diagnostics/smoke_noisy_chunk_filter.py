#!/usr/bin/env python3
"""
test_noisy_chunk_filter.py
==========================
Phase 1.5 Step 6.5 – Tests for noisy chunk detection heuristics.

No LlamaParse, no Qdrant, no Neo4j, no LLM needed.

Usage
-----
    python scripts/diagnostics/smoke_noisy_chunk_filter.py
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

from scripts.ingest_knowledge import chunk_markdown_text, is_noisy_chunk

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
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
# Test cases for is_noisy_chunk()
# ─────────────────────────────────────────────────────────────────────────────

TEST_CASES: list[tuple[str, str | None, bool, str]] = [
    # (text, header, expected_noisy, test_label)

    # ── Should be NOISY ──────────────────────────────────────────────

    (
        "." * 80 + " 53",
        None,
        True,
        "Dots + page number → noisy",
    ),
    (
        "- **Terms used in this guideline** ..............."
        "......................................................................."
        "................ 12\n"
        "- **Overview** ................................................."
        "......................................................................."
        "...... 5",
        "Contents",
        True,
        "TOC dot-leaders under 'Contents' header → noisy",
    ),
    (
        "© NICE 2024. All rights reserved. Subject to Notice of rights.",
        "Contents",
        True,
        "Copyright notice → noisy",
    ),
    (
        "42",
        None,
        True,
        "Single page number → noisy (too short, no medical keyword)",
    ),
    (
        "some short text",
        None,
        True,
        "Short text (<80 chars) without medical keyword → noisy",
    ),
    (
        "." * 100,
        "Maintenance",
        True,
        "All dots under 'Maintenance' header → noisy",
    ),
    (
        "12\n45\n78\n99",
        None,
        True,
        "Multiple page numbers → noisy",
    ),

    # ── Should NOT be noisy ──────────────────────────────────────────

    (
        "Formulation with: 5% benzoyl peroxide",
        None,
        False,
        "Short but contains 'benzoyl peroxide' → rescued by medical keyword",
    ),
    (
        "0.1% adapalene topical gel",
        None,
        False,
        "Short but contains 'adapalene' + 'topical' → rescued",
    ),
    (
        "An ingredient that is likely to block skin pores.",
        "Comedogenic",
        False,
        "Short but contains comedogenic keyword → rescued",
    ),
    (
        "Tretinoin 0.025% cream nên bôi vào buổi tối.",
        None,
        False,
        "Short but contains 'tretinoin' + 'cream' + 'bôi' → rescued",
    ),
    (
        "Mụn trứng cá có thể liên quan đến tăng tiết bã nhờn, "
        "bít tắc nang lông và vi khuẩn C. acnes.",
        "Causes",
        False,
        "Normal medical content (≥80 chars) → not noisy",
    ),
    (
        "Benzoyl peroxide và retinoid thường được nhắc đến trong "
        "điều trị mụn viêm. Salicylic acid cũng phổ biến.",
        "Treatment",
        False,
        "Treatment text with ingredients → not noisy",
    ),
    (
        "Consider referral to mental health services if a person "
        "with acne experiences significant psychological distress.",
        "1.4.5",
        False,
        "Clinical recommendation (≥80 chars) → not noisy",
    ),
]


def run_direct_tests() -> bool:
    """Test is_noisy_chunk() directly with individual test cases."""
    global all_ok

    print("\n─── Direct is_noisy_chunk() tests ───\n")

    for text, header, expected_noisy, label in TEST_CASES:
        noisy, reason = is_noisy_chunk(text, header)
        status = "noisy" if noisy else "clean"
        expected = "noisy" if expected_noisy else "clean"

        match = (noisy == expected_noisy)
        assert_true(
            f"[{expected}] {label} → got {status}"
            + (f" ({reason})" if noisy else ""),
            match,
        )

    return all_ok


def run_pipeline_tests() -> bool:
    """Test that chunk_markdown_text() tags chunks with is_noisy."""
    global all_ok

    print("\n─── Pipeline integration tests ───\n")

    markdown = """\
# Acne

## Contents
- **Overview** ......................................................................................
.....................................................................................................
.....................................................................................................

## Treatment
Benzoyl peroxide và retinoid thường được nhắc đến trong điều trị mụn viêm.
Salicylic acid cũng được sử dụng phổ biến trong chăm sóc da dầu mụn.

## Notice
© NICE 2024. All rights reserved.
"""

    chunks = chunk_markdown_text(
        markdown_text=markdown,
        source_file="test_noisy.pdf",
        max_section_chars=2000,
    )

    print(f"  Total chunks: {len(chunks)}\n")

    noisy_count = 0
    clean_count = 0

    for i, c in enumerate(chunks):
        is_n = c.metadata.get("is_noisy", False)
        reason = c.metadata.get("noise_reason", None)
        status = "🔇 NOISY" if is_n else "✅ CLEAN"
        preview = c.text[:60].replace("\n", " ")

        if is_n:
            noisy_count += 1
        else:
            clean_count += 1

        print(f"  [{i}] {status}  header={c.header_path!r}  "
              f"reason={reason or '—'}")
        print(f"       text: {preview}…")

    print()

    # Assertions
    assert_true(
        f"At least 1 noisy chunk detected (got {noisy_count})",
        noisy_count >= 1,
    )
    assert_true(
        f"At least 1 clean chunk exists (got {clean_count})",
        clean_count >= 1,
    )

    # The Treatment chunk should be clean
    treatment_chunks = [c for c in chunks if c.header_path == "Treatment"]
    for tc in treatment_chunks:
        assert_true(
            f"Treatment chunk is clean (is_noisy={tc.metadata.get('is_noisy')})",
            tc.metadata.get("is_noisy") is False,
        )

    # Contents chunk should be noisy
    contents_chunks = [c for c in chunks if c.header_path == "Contents"]
    for cc in contents_chunks:
        if "..." in cc.text:
            assert_true(
                f"Contents+dots chunk is noisy (is_noisy={cc.metadata.get('is_noisy')})",
                cc.metadata.get("is_noisy") is True,
            )

    # All chunks must have is_noisy field
    for c in chunks:
        assert_true(
            f"Chunk {c.chunk_index} has 'is_noisy' in metadata",
            "is_noisy" in c.metadata,
        )

    # Dermatology metadata still present
    assert_true(
        "Dermatology metadata still present on Treatment chunk",
        "domain_topic" in treatment_chunks[0].metadata if treatment_chunks else False,
    )

    # Hierarchical metadata still present
    assert_true(
        "Hierarchical metadata still present on Treatment chunk",
        "parent_id" in treatment_chunks[0].metadata if treatment_chunks else False,
    )

    return all_ok


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  Phase 1.5 Step 6.5 – Noisy Chunk Filter Tests")
    print("=" * 60)

    run_direct_tests()
    run_pipeline_tests()

    print("\n" + "=" * 60)
    if all_ok:
        print("  ALL TESTS PASSED ✅")
    else:
        print("  SOME TESTS FAILED ❌")
    print("=" * 60)

    sys.exit(0 if all_ok else 1)
