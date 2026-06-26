#!/usr/bin/env python3
"""
test_dermatology_metadata.py
============================
Phase 1.5 – Smoke tests for the dermatology taxonomy and metadata extractor.

Runs five test cases and verifies expected metadata fields.
Exit code 0 if all pass, 1 otherwise.

Usage
-----
    python scripts/diagnostics/smoke_dermatology_metadata.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Bootstrap – ensure project root is on sys.path
# ─────────────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ingestion.domain_metadata import extract_dermatology_metadata


# ─────────────────────────────────────────────────────────────────────────────
# Test helpers
# ─────────────────────────────────────────────────────────────────────────────

PASS = "✅ PASS"
FAIL = "❌ FAIL"


def check(
    label: str,
    meta: dict,
    field: str,
    expected: set[str],
    mode: str = "any",
) -> bool:
    """
    Verify that *meta[field]* contains the expected values.

    Parameters
    ----------
    mode : str
        - ``"any"``:  at least one of *expected* is in the result.
        - ``"all"``:  all of *expected* are in the result.
    """
    actual = set(meta.get(field, []))
    if mode == "any":
        ok = bool(actual & expected)
    else:
        ok = expected.issubset(actual)

    status = PASS if ok else FAIL
    print(f"  {status}  {label}")
    if not ok:
        print(f"         expected ({mode}): {expected}")
        print(f"         actual:           {actual}")
    return ok


# ─────────────────────────────────────────────────────────────────────────────
# Test cases
# ─────────────────────────────────────────────────────────────────────────────

def run_tests() -> bool:
    all_ok = True

    # ── Test 1 ──────────────────────────────────────────────────────────
    print("\n─── Test 1: Da dầu + mụn viêm ───")
    text1 = "Da dầu bị mụn viêm nên chú ý gì?"
    meta1 = extract_dermatology_metadata(text1)
    print(f"  Input : {text1}")
    print(f"  Output: {json.dumps(meta1, ensure_ascii=False, indent=4)}")
    all_ok &= check("skin_type contains oily", meta1, "skin_type", {"oily"})
    all_ok &= check(
        "concern contains inflammatory_acne or acne",
        meta1, "concern", {"inflammatory_acne", "acne"}, mode="any",
    )
    all_ok &= meta1["confidence"] > 0.0
    print(f"  confidence = {meta1['confidence']}")

    # ── Test 2 ──────────────────────────────────────────────────────────
    print("\n─── Test 2: Benzoyl peroxide side effects ───")
    text2 = "Benzoyl peroxide có thể gây khô da, đỏ, kích ứng."
    meta2 = extract_dermatology_metadata(text2)
    print(f"  Input : {text2}")
    print(f"  Output: {json.dumps(meta2, ensure_ascii=False, indent=4)}")
    all_ok &= check("ingredient contains benzoyl_peroxide", meta2, "ingredient", {"benzoyl_peroxide"})
    all_ok &= check(
        "safety_context contains dryness or irritation",
        meta2, "safety_context", {"dryness", "irritation"}, mode="any",
    )
    all_ok &= check(
        "content_type contains side_effect",
        meta2, "content_type", {"side_effect"}, mode="any",
    )

    # ── Test 3 ──────────────────────────────────────────────────────────
    print("\n─── Test 3: Retinoid peeling / irritation ───")
    text3 = "Retinoid có thể gây bong tróc và kích ứng da."
    meta3 = extract_dermatology_metadata(text3)
    print(f"  Input : {text3}")
    print(f"  Output: {json.dumps(meta3, ensure_ascii=False, indent=4)}")
    all_ok &= check("ingredient contains retinoid", meta3, "ingredient", {"retinoid"})
    all_ok &= check(
        "safety_context contains peeling and irritation",
        meta3, "safety_context", {"peeling", "irritation"}, mode="all",
    )

    # ── Test 4 ──────────────────────────────────────────────────────────
    print("\n─── Test 4: Pregnancy safety ───")
    text4 = "Phụ nữ mang thai cần thận trọng khi dùng thuốc trị mụn."
    meta4 = extract_dermatology_metadata(text4)
    print(f"  Input : {text4}")
    print(f"  Output: {json.dumps(meta4, ensure_ascii=False, indent=4)}")
    all_ok &= check(
        "safety_context contains pregnancy_safety",
        meta4, "safety_context", {"pregnancy_safety"},
    )

    # ── Test 5 ──────────────────────────────────────────────────────────
    print("\n─── Test 5: Blackheads on nose ───")
    text5 = "Mụn đầu đen ở mũi có nên nặn không?"
    meta5 = extract_dermatology_metadata(text5)
    print(f"  Input : {text5}")
    print(f"  Output: {json.dumps(meta5, ensure_ascii=False, indent=4)}")
    all_ok &= check("concern contains blackheads", meta5, "concern", {"blackheads"})
    all_ok &= check("body_area contains nose", meta5, "body_area", {"nose"})

    # ── Test 6 ──────────────────────────────────────────────────────────
    print("\n─── Test 6: 'khô da' as side effect → safety_context=dryness, NOT skin_type=dry ───")
    text6 = "Benzoyl peroxide có thể gây khô da không?"
    meta6 = extract_dermatology_metadata(text6)
    print(f"  Input : {text6}")
    print(f"  Output: {json.dumps(meta6, ensure_ascii=False, indent=4)}")
    all_ok &= check(
        "safety_context contains dryness",
        meta6, "safety_context", {"dryness"},
    )
    ok6_no_dry = "dry" not in meta6.get("skin_type", [])
    status6 = PASS if ok6_no_dry else FAIL
    print(f"  {status6}  skin_type does NOT contain 'dry'")
    if not ok6_no_dry:
        print(f"         actual skin_type: {meta6.get('skin_type', [])}")
    all_ok &= ok6_no_dry

    # ── Test 7 ──────────────────────────────────────────────────────────
    print("\n─── Test 7: 'da khô' as skin type → skin_type=dry, NOT safety_context=dryness ───")
    text7 = "Tôi có da khô bị mụn thì dùng gì?"
    meta7 = extract_dermatology_metadata(text7)
    print(f"  Input : {text7}")
    print(f"  Output: {json.dumps(meta7, ensure_ascii=False, indent=4)}")
    all_ok &= check(
        "skin_type contains dry",
        meta7, "skin_type", {"dry"},
    )
    ok7_no_dryness = "dryness" not in meta7.get("safety_context", [])
    status7 = PASS if ok7_no_dryness else FAIL
    print(f"  {status7}  safety_context does NOT contain 'dryness'")
    if not ok7_no_dryness:
        print(f"         actual safety_context: {meta7.get('safety_context', [])}")
    all_ok &= ok7_no_dryness

    # ── Test 8 ──────────────────────────────────────────────────────────
    print("\n─── Test 8: English 'skin dryness' + 'irritation' ───")
    text8 = "Benzoyl peroxide may cause skin dryness and irritation."
    meta8 = extract_dermatology_metadata(text8)
    print(f"  Input : {text8}")
    print(f"  Output: {json.dumps(meta8, ensure_ascii=False, indent=4)}")
    all_ok &= check(
        "safety_context contains dryness",
        meta8, "safety_context", {"dryness"},
    )
    all_ok &= check(
        "safety_context contains irritation",
        meta8, "safety_context", {"irritation"},
    )

    # ── Test 9 ──────────────────────────────────────────────────────────
    print("\n─── Test 9: English 'drying' keyword ───")
    text9 = "This product may be drying."
    meta9 = extract_dermatology_metadata(text9)
    print(f"  Input : {text9}")
    print(f"  Output: {json.dumps(meta9, ensure_ascii=False, indent=4)}")
    all_ok &= check(
        "safety_context contains dryness",
        meta9, "safety_context", {"dryness"},
    )

    # ── Test 10 ─────────────────────────────────────────────────────────
    print("\n─── Test 10: Clinical 'xerosis' keyword ───")
    text10 = "Patients with xerosis should be careful."
    meta10 = extract_dermatology_metadata(text10)
    print(f"  Input : {text10}")
    print(f"  Output: {json.dumps(meta10, ensure_ascii=False, indent=4)}")
    all_ok &= check(
        "safety_context contains dryness",
        meta10, "safety_context", {"dryness"},
    )

    # ── Extraction method ──────────────────────────────────────────────
    print("\n─── Global checks ───")
    all_metas = [meta1, meta2, meta3, meta4, meta5, meta6, meta7, meta8, meta9, meta10]
    for i, m in enumerate(all_metas, 1):
        ok = m["extraction_method"] == "rule_based"
        status = PASS if ok else FAIL
        print(f"  {status}  Test {i} extraction_method == 'rule_based'")
        all_ok &= ok

    return all_ok


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  Phase 1.5 – Dermatology Metadata Extractor Tests")
    print("=" * 60)

    success = run_tests()

    print("\n" + "=" * 60)
    if success:
        print("  ALL TESTS PASSED ✅")
    else:
        print("  SOME TESTS FAILED ❌")
    print("=" * 60)

    sys.exit(0 if success else 1)
