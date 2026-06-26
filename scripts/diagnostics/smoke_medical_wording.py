#!/usr/bin/env python3
"""
test_medical_wording.py
=======================
Phase 2 – Tests for medical safety wording post-processing and safety flags.

Verifies:
  1. Pregnancy category removal ("thai kỳ C/X" → safe wording)
  2. Translation fixes ("cắn môi" → "môi nứt nẻ", "nhiễm ánh sáng" → "nhạy cảm với ánh sáng")
  3. Isotretinoin scar wording fix
  4. Retinoid comparative safety
  5. Topical antibiotic monotherapy warning
  6. Retinoid + pregnancy safety flags (5 retinoid × multiple pregnancy keywords)
  7. Non-pregnancy queries do NOT trigger false positive safety flags

No LLM, no Qdrant, no Neo4j needed.

Usage
-----
    python scripts/diagnostics/smoke_medical_wording.py
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Bootstrap
# ─────────────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.nodes.respond import finalize_response_node
from src.agent.nodes.reason import safety_check_node

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


def make_state(draft: str, user_question: str = "") -> dict:
    """Build a minimal ClinicalState-like dict for finalize_response_node."""
    return {
        "is_in_domain": True,
        "cache_hit": False,
        "draft_answer": draft,
        "user_question": user_question,
    }


def make_safety_state(question: str) -> dict:
    """Build a minimal state dict for safety_check_node."""
    return {
        "normalized_question": question,
        "symptoms": [],
    }


async def post_process(draft: str, user_question: str = "") -> str:
    """Run finalize_response_node and return the final_answer."""
    state = make_state(draft, user_question)
    result = await finalize_response_node(state)
    return result.get("final_answer", "")


async def get_safety_flags(question: str) -> list[str]:
    """Run safety_check_node and return the flags."""
    state = make_safety_state(question)
    result = await safety_check_node(state)
    return result.get("safety_flags", [])


# ─────────────────────────────────────────────────────────────────────────────
# Post-processing tests
# ─────────────────────────────────────────────────────────────────────────────

async def run_postprocess_tests() -> None:
    global all_ok

    # ── Test 1: "cắn môi" → "môi nứt nẻ" ─────────────────────────────
    print("\n─── Test 1: 'cắn môi' → 'môi nứt nẻ' ───")
    out1 = await post_process("Isotretinoin có thể gây cắn môi và khô da.")
    assert_true("'cắn môi' NOT in output", "cắn môi" not in out1)
    assert_true("'môi nứt nẻ' in output", "môi nứt nẻ" in out1)
    print(f"  → {out1[:80]}")

    # ── Test 2: "nhiễm ánh sáng" → "nhạy cảm với ánh sáng" ──────────
    print("\n─── Test 2: 'nhiễm ánh sáng' → 'nhạy cảm với ánh sáng' ───")
    out2 = await post_process("Retinoid có thể gây nhiễm ánh sáng cho da.")
    assert_true("'nhiễm ánh sáng' NOT in output", "nhiễm ánh sáng" not in out2)
    assert_true("'nhạy cảm với ánh sáng' in output", "nhạy cảm với ánh sáng" in out2)
    print(f"  → {out2[:80]}")

    # ── Test 3: "thai kỳ C" without "phân loại cũ" ───────────────────
    print("\n─── Test 3: 'thai kỳ C' removed (no 'phân loại cũ') ───")
    out3 = await post_process("Thuốc này thuộc thai kỳ C nên cần thận trọng.")
    assert_true("'thai kỳ C' NOT in output", "thai kỳ C" not in out3.lower())
    assert_true("safe wording present", "bác sĩ" in out3.lower())
    print(f"  → {out3[:100]}")

    # ── Test 4: "thai kỳ X" removed ──────────────────────────────────
    print("\n─── Test 4: 'thai kỳ X' removed ───")
    out4 = await post_process("Isotretinoin thuộc thai kỳ X, chống chỉ định mang thai.")
    assert_true("'thai kỳ X' NOT in output", "thai kỳ x" not in out4.lower())
    assert_true("safe wording present", "bác sĩ" in out4.lower() or "mang thai" in out4.lower())
    print(f"  → {out4[:100]}")

    # ── Test 5: "phân loại cũ, thai kỳ C" → ALLOWED ─────────────────
    print("\n─── Test 5: 'phân loại cũ, thai kỳ C' allowed ───")
    text5 = "Theo phân loại cũ, thai kỳ C là nhóm chưa có đủ bằng chứng."
    out5 = await post_process(text5)
    # The "phân loại cũ" prefix should protect the phrase
    assert_true("'phân loại cũ' preserved in output", "phân loại cũ" in out5)
    print(f"  → {out5[:100]}")

    # ── Test 6: "isotretinoin gây nguy cơ sẹo" → rewrite ────────────
    print("\n─── Test 6: 'isotretinoin gây nguy cơ sẹo' → rewrite ───")
    out6 = await post_process("Nếu isotretinoin gây nguy cơ sẹo thì phải làm sao?")
    assert_true("'gây nguy cơ sẹo' NOT in output", "gây nguy cơ sẹo" not in out6)
    assert_true("'cân nhắc cho mụn nặng' in output", "cân nhắc cho mụn nặng" in out6)
    print(f"  → {out6[:120]}")

    # ── Test 7: "isotretinoin gây sẹo" → rewrite ────────────────────
    print("\n─── Test 7: 'isotretinoin gây sẹo' → rewrite ───")
    out7 = await post_process("Dùng isotretinoin gây sẹo nhiều hơn phải không?")
    assert_true("'gây sẹo' NOT in output", "gây sẹo" not in out7)
    assert_true("'cân nhắc cho mụn nặng' in output", "cân nhắc cho mụn nặng" in out7)
    print(f"  → {out7[:120]}")

    # ── Test 8: Topical antibiotic warning – clindamycin ─────────────
    print("\n─── Test 8: clindamycin bôi → antibiotic resistance warning ───")
    text8 = (
        "Clindamycin bôi là một lựa chọn cho mụn viêm.\n\n"
        "Thông tin này chỉ mang tính tham khảo và không thay thế tư vấn y khoa chuyên nghiệp."
    )
    out8 = await post_process(text8)
    has_abx_warning = ("kháng kháng sinh" in out8 or "benzoyl peroxide" in out8.lower())
    assert_true("antibiotic resistance warning present", has_abx_warning)
    print(f"  → ...{out8[-120:]}")

    # ── Test 9: Topical antibiotic – erythromycin ────────────────────
    print("\n─── Test 9: erythromycin bôi → antibiotic resistance warning ───")
    text9 = (
        "Erythromycin gel có thể dùng cho mụn viêm nhẹ.\n\n"
        "Thông tin này chỉ mang tính tham khảo và không thay thế tư vấn y khoa chuyên nghiệp."
    )
    out9 = await post_process(text9)
    has_abx_warning9 = ("kháng kháng sinh" in out9 or "benzoyl peroxide" in out9.lower())
    assert_true("antibiotic resistance warning present", has_abx_warning9)
    print(f"  → ...{out9[-120:]}")

    # ── Test 10: No double warning if already has BP ─────────────────
    print("\n─── Test 10: No double warning if already mentions phối hợp ───")
    text10 = (
        "Clindamycin nên phối hợp với benzoyl peroxide.\n\n"
        "Thông tin này chỉ mang tính tham khảo và không thay thế tư vấn y khoa chuyên nghiệp."
    )
    out10 = await post_process(text10)
    count_khang = out10.lower().count("kháng kháng sinh")
    assert_true(f"No extra 'kháng kháng sinh' appended (count={count_khang})", count_khang == 0)
    print(f"  → OK (phối hợp already present, no duplicate)")

    # ── Test 11: "pregnancy category X" → rewrite ────────────────────
    print("\n─── Test 11: 'pregnancy category X' → rewrite ───")
    out11 = await post_process("This drug is FDA pregnancy category X.")
    assert_true("'category X' NOT in output", "category x" not in out11.lower())
    assert_true("safe wording present", "bác sĩ" in out11.lower() or "mang thai" in out11.lower())
    print(f"  → {out11[:100]}")

    # ── Test 12: Retinoid comparative safety ──────────────────────────
    print("\n─── Test 12: 'tretinoin ít nguy hiểm hơn' → rewrite ───")
    out12 = await post_process("Tretinoin ít nguy hiểm hơn adapalen cho thai phụ.")
    assert_true("'ít nguy hiểm hơn' NOT in output", "ít nguy hiểm hơn" not in out12)
    assert_true("'bác sĩ đánh giá lợi ích-nguy cơ' in output", "lợi ích-nguy cơ" in out12)
    print(f"  → {out12[:120]}")

    # ── Test 13: Normal BP text NOT incorrectly rewritten ────────────
    print("\n─── Test 13: Normal benzoyl peroxide text preserved ───")
    text13 = "Benzoyl peroxide là hoạt chất thường được nhắc đến trong điều trị mụn viêm."
    out13 = await post_process(text13)
    assert_true("Original text preserved", "thường được nhắc đến" in out13)
    print(f"  → {out13[:80]}")


# ─────────────────────────────────────────────────────────────────────────────
# Safety flag tests
# ─────────────────────────────────────────────────────────────────────────────

async def run_safety_flag_tests() -> None:
    global all_ok

    # ── Test S1: retinoid + mang thai ─────────────────────────────────
    print("\n─── Test S1: retinoid + mang thai → safety flag ───")
    flags_s1 = await get_safety_flags("Dùng retinoid khi mang thai có an toàn không?")
    assert_true(f"Flags not empty ({len(flags_s1)} flags)", len(flags_s1) > 0)
    assert_true("Flag mentions retinoid", any("retinoid" in f.lower() for f in flags_s1))

    # ── Test S2: adapalen + mang thai ─────────────────────────────────
    print("\n─── Test S2: adapalen + mang thai → safety flag ───")
    flags_s2 = await get_safety_flags("Adapalen có dùng được khi mang thai không?")
    assert_true(f"Flags not empty ({len(flags_s2)} flags)", len(flags_s2) > 0)
    assert_true("Flag mentions adapalen", any("adapalen" in f.lower() for f in flags_s2))

    # ── Test S3: tretinoin + có bầu ──────────────────────────────────
    print("\n─── Test S3: tretinoin + có bầu → safety flag ───")
    flags_s3 = await get_safety_flags("Tretinoin có dùng được khi có bầu không?")
    assert_true(f"Flags not empty ({len(flags_s3)} flags)", len(flags_s3) > 0)
    assert_true("Flag mentions tretinoin", any("tretinoin" in f.lower() for f in flags_s3))

    # ── Test S4: tazarotene + pregnancy ──────────────────────────────
    print("\n─── Test S4: tazarotene + pregnancy → safety flag ───")
    flags_s4 = await get_safety_flags("Is tazarotene safe during pregnancy?")
    assert_true(f"Flags not empty ({len(flags_s4)} flags)", len(flags_s4) > 0)
    assert_true("Flag mentions tazarotene", any("tazarotene" in f.lower() for f in flags_s4))

    # ── Test S5: isotretinoin + chuẩn bị mang thai ───────────────────
    print("\n─── Test S5: isotretinoin + chuẩn bị mang thai → safety flag ───")
    flags_s5 = await get_safety_flags("Tôi đang chuẩn bị mang thai, dùng isotretinoin có sao không?")
    assert_true(f"Flags not empty ({len(flags_s5)} flags)", len(flags_s5) > 0)
    assert_true("Flag mentions isotretinoin", any("isotretinoin" in f.lower() for f in flags_s5))

    # ── Test S6: benzoyl peroxide (no pregnancy) → NO flag ───────────
    print("\n─── Test S6: benzoyl peroxide (no pregnancy) → NO safety flag ───")
    flags_s6 = await get_safety_flags("Benzoyl peroxide có tác dụng phụ gì?")
    pregnancy_flags = [f for f in flags_s6 if "thai" in f.lower() or "mang thai" in f.lower() or "pregnancy" in f.lower()]
    assert_true(f"No pregnancy flag for BP ({len(pregnancy_flags)} pregnancy flags)", len(pregnancy_flags) == 0)

    # ── Test S7: retinoid alone (no pregnancy) → NO flag ─────────────
    print("\n─── Test S7: retinoid alone (no pregnancy) → NO safety flag ───")
    flags_s7 = await get_safety_flags("Retinoid có gây kích ứng không?")
    pregnancy_flags_s7 = [f for f in flags_s7 if "thai" in f.lower() or "mang thai" in f.lower() or "pregnancy" in f.lower()]
    assert_true(f"No pregnancy flag for retinoid only ({len(pregnancy_flags_s7)} flags)", len(pregnancy_flags_s7) == 0)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

async def main() -> int:
    global all_ok

    print("=" * 60)
    print("  Phase 2 – Medical Wording & Safety Tests")
    print("=" * 60)

    print("\n" + "─" * 60)
    print("  SECTION A: Post-Processing Tests")
    print("─" * 60)
    await run_postprocess_tests()

    print("\n" + "─" * 60)
    print("  SECTION B: Safety Flag Tests")
    print("─" * 60)
    await run_safety_flag_tests()

    print("\n" + "=" * 60)
    if all_ok:
        print("  ALL TESTS PASSED ✅")
    else:
        print("  SOME TESTS FAILED ❌")
    print("=" * 60)

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
