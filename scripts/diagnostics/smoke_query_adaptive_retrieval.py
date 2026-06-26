#!/usr/bin/env python3
"""
test_query_adaptive_retrieval.py
================================
Phase 1.5 Step 4 – Tests for query-adaptive dermatology retrieval boost.

Tests extract_query_dermatology_metadata() and apply_metadata_boost()
with fake results.  No backend, no Qdrant, no Neo4j needed.

Usage
-----
    python scripts/diagnostics/smoke_query_adaptive_retrieval.py
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

from src.database.retriever import (
    _MAX_METADATA_BOOST,
    apply_metadata_boost,
    extract_query_dermatology_metadata,
)

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


def make_fake_result(
    doc_id: str,
    score: float,
    **payload: object,
) -> dict:
    """Build a fake retrieval result dict matching Qdrant output shape."""
    return {"id": doc_id, "score": score, **payload}


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

def run_tests() -> bool:
    global all_ok

    # ══════════════════════════════════════════════════════════════════
    # Test 1: Query metadata – "Da dầu bị mụn nên dùng gì?"
    # ══════════════════════════════════════════════════════════════════
    print("\n─── Test 1: Query metadata – oily skin + acne ───")
    q1 = "Da dầu bị mụn nên dùng gì?"
    m1 = extract_query_dermatology_metadata(q1)
    print(f"  Query: {q1}")
    print(f"  skin_type: {m1.get('skin_type')}")
    print(f"  concern:   {m1.get('concern')}")

    assert_true(
        "skin_type contains 'oily'",
        "oily" in m1.get("skin_type", []),
    )
    assert_true(
        "concern contains 'acne' or 'inflammatory_acne'",
        bool({"acne", "inflammatory_acne"} & set(m1.get("concern", []))),
    )

    # ══════════════════════════════════════════════════════════════════
    # Test 2: Query metadata – "Retinoid có gây kích ứng không?"
    # ══════════════════════════════════════════════════════════════════
    print("\n─── Test 2: Query metadata – retinoid + irritation ───")
    q2 = "Retinoid có gây kích ứng không?"
    m2 = extract_query_dermatology_metadata(q2)
    print(f"  Query: {q2}")
    print(f"  ingredient:     {m2.get('ingredient')}")
    print(f"  safety_context: {m2.get('safety_context')}")
    print(f"  content_type:   {m2.get('content_type')}")

    assert_true(
        "ingredient contains 'retinoid'",
        "retinoid" in m2.get("ingredient", []),
    )
    assert_true(
        "safety_context contains 'irritation' or content_type contains 'side_effect'",
        "irritation" in m2.get("safety_context", [])
        or "side_effect" in m2.get("content_type", []),
    )

    # ══════════════════════════════════════════════════════════════════
    # Test 3: Boost ranking – oily + acne + treatment vs dry + definition
    # ══════════════════════════════════════════════════════════════════
    print("\n─── Test 3: Boost ranking – matching vs non-matching ───")
    q3 = "Da dầu bị mụn nên dùng gì?"
    m3 = extract_query_dermatology_metadata(q3)

    result_a = make_fake_result(
        "A", 0.70,
        text="Dùng benzoyl peroxide cho da dầu bị mụn",
        skin_type=["oily"],
        concern=["acne"],
        content_type=["treatment"],
        ingredient=["benzoyl_peroxide"],
        domain_topic=["acne_treatment"],
        safety_context=[],
        body_area=[],
    )
    result_b = make_fake_result(
        "B", 0.72,
        text="Định nghĩa da khô là gì",
        skin_type=["dry"],
        concern=["acne"],
        content_type=["definition"],
        ingredient=[],
        domain_topic=[],
        safety_context=[],
        body_area=[],
    )

    boosted3 = apply_metadata_boost([result_a, result_b], m3)
    a3 = next(r for r in boosted3 if r["id"] == "A")
    b3 = next(r for r in boosted3 if r["id"] == "B")

    print(f"  A: original={a3['original_score']}, boost={a3['metadata_boost']}, "
          f"boosted={a3['boosted_score']}, matched={a3['matched_metadata_fields']}")
    print(f"  B: original={b3['original_score']}, boost={b3['metadata_boost']}, "
          f"boosted={b3['boosted_score']}, matched={b3['matched_metadata_fields']}")

    assert_true(
        f"A boosted_score ({a3['boosted_score']}) > B boosted_score ({b3['boosted_score']})",
        a3["boosted_score"] > b3["boosted_score"],
    )
    assert_true(
        "A metadata_boost_applied is True",
        a3["metadata_boost_applied"] is True,
    )

    # ══════════════════════════════════════════════════════════════════
    # Test 4: Boost ranking – retinoid + irritation vs benzoyl + treatment
    # ══════════════════════════════════════════════════════════════════
    print("\n─── Test 4: Boost ranking – retinoid side effect query ───")
    q4 = "Retinoid có gây kích ứng không?"
    m4 = extract_query_dermatology_metadata(q4)

    result_c = make_fake_result(
        "C", 0.65,
        text="Retinoid gây kích ứng da",
        ingredient=["retinoid"],
        safety_context=["irritation"],
        content_type=["side_effect"],
        concern=[],
        skin_type=[],
        domain_topic=["side_effect"],
        body_area=[],
    )
    result_d = make_fake_result(
        "D", 0.68,
        text="Benzoyl peroxide trong điều trị mụn",
        ingredient=["benzoyl_peroxide"],
        content_type=["treatment"],
        concern=["acne"],
        safety_context=[],
        skin_type=[],
        domain_topic=["acne_treatment"],
        body_area=[],
    )

    boosted4 = apply_metadata_boost([result_c, result_d], m4)
    c4 = next(r for r in boosted4 if r["id"] == "C")
    d4 = next(r for r in boosted4 if r["id"] == "D")

    print(f"  C: original={c4['original_score']}, boost={c4['metadata_boost']}, "
          f"boosted={c4['boosted_score']}, matched={c4['matched_metadata_fields']}")
    print(f"  D: original={d4['original_score']}, boost={d4['metadata_boost']}, "
          f"boosted={d4['boosted_score']}, matched={d4['matched_metadata_fields']}")

    assert_true(
        f"C boosted_score ({c4['boosted_score']}) > D boosted_score ({d4['boosted_score']})",
        c4["boosted_score"] > d4["boosted_score"],
    )

    # ══════════════════════════════════════════════════════════════════
    # Test 5: Backward compatibility – no payload / no metadata fields
    # ══════════════════════════════════════════════════════════════════
    print("\n─── Test 5: Backward compatibility – missing metadata ───")
    result_empty = {"id": "E", "score": 0.60, "text": "Some old chunk"}
    result_none_score = {"id": "F", "text": "Chunk with no score"}
    result_no_lists = {"id": "G", "score": 0.55, "ingredient": "not_a_list"}

    try:
        boosted5 = apply_metadata_boost(
            [result_empty, result_none_score, result_no_lists],
            m3,
        )
        assert_true("No crash with missing metadata", True)
        assert_true(
            f"All 3 results returned ({len(boosted5)})",
            len(boosted5) == 3,
        )

        e5 = next(r for r in boosted5 if r["id"] == "E")
        assert_true(
            "E metadata_boost_applied is False",
            e5["metadata_boost_applied"] is False,
        )

        f5 = next(r for r in boosted5 if r["id"] == "F")
        assert_true(
            f"F original_score is 0.0 (was None) → {f5['original_score']}",
            f5["original_score"] == 0.0,
        )

        g5 = next(r for r in boosted5 if r["id"] == "G")
        assert_true(
            "G not crashed despite ingredient='not_a_list'",
            g5["metadata_boost_applied"] is False,
        )
    except Exception as exc:
        assert_true(f"No crash with missing metadata (got: {exc})", False)

    # ══════════════════════════════════════════════════════════════════
    # Test 6: Boost cap does not exceed _MAX_METADATA_BOOST
    # ══════════════════════════════════════════════════════════════════
    print(f"\n─── Test 6: Boost cap ≤ {_MAX_METADATA_BOOST} ───")

    # Create a result that matches ALL fields to test cap
    result_all_match = make_fake_result(
        "H", 0.50,
        text="Everything matches",
        ingredient=["retinoid", "benzoyl_peroxide"],
        concern=["acne", "inflammatory_acne"],
        content_type=["treatment", "side_effect"],
        domain_topic=["acne_treatment", "side_effect"],
        skin_type=["oily"],
        safety_context=["irritation", "dryness"],
        body_area=["face", "nose"],
    )

    # Use a query that matches many fields
    q6 = "Da dầu mặt bị mụn viêm, dùng retinoid có gây kích ứng khô da không?"
    m6 = extract_query_dermatology_metadata(q6)
    print(f"  Query metadata fields populated:")
    for f in ["ingredient", "concern", "content_type", "domain_topic",
              "skin_type", "safety_context", "body_area"]:
        print(f"    {f}: {m6.get(f, [])}")

    boosted6 = apply_metadata_boost([result_all_match], m6)
    h6 = boosted6[0]

    print(f"  H: original={h6['original_score']}, boost={h6['metadata_boost']}, "
          f"boosted={h6['boosted_score']}")
    print(f"  matched: {h6['matched_metadata_fields']}")

    assert_true(
        f"metadata_boost ({h6['metadata_boost']}) <= {_MAX_METADATA_BOOST}",
        h6["metadata_boost"] <= _MAX_METADATA_BOOST,
    )
    assert_true(
        f"boosted_score ({h6['boosted_score']}) == original + capped_boost",
        abs(h6["boosted_score"] - (0.50 + h6["metadata_boost"])) < 1e-9,
    )

    # ══════════════════════════════════════════════════════════════════
    # Test 7: Debug metadata fields present
    # ══════════════════════════════════════════════════════════════════
    print("\n─── Test 7: Debug metadata fields present ───")
    debug_fields = [
        "original_score", "metadata_boost", "boosted_score",
        "metadata_boost_applied", "matched_metadata_fields",
    ]
    sample = boosted3[0]
    for df in debug_fields:
        assert_true(f"'{df}' present in result", df in sample)

    return all_ok


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  Phase 1.5 Step 4 – Query-Adaptive Retrieval Tests")
    print("=" * 60)

    success = run_tests()

    print("\n" + "=" * 60)
    if success:
        print("  ALL TESTS PASSED ✅")
    else:
        print("  SOME TESTS FAILED ❌")
    print("=" * 60)

    sys.exit(0 if success else 1)
