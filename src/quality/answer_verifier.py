"""Rule-based answer quality verifier and guard.

The verifier is deterministic and offline-only. It never calls LLMs or
external APIs.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from src.retrieval.contracts import NormalizedQuery, PackedContext, RetrievalTrace
from src.retrieval.query_normalization import normalize_query
from src.quality.contracts import (
    AnswerGuardResult,
    AnswerQualityIssue,
    AnswerVerificationReport,
)


CRITICAL = "critical"
ERROR = "error"
WARNING = "warning"


def verify_answer_quality(
    query: str,
    answer: str,
    normalized_query: NormalizedQuery | None = None,
    packed_context: PackedContext | None = None,
    retrieval_trace: RetrievalTrace | None = None,
) -> AnswerVerificationReport:
    """Verify answer quality with deterministic medical/domain rules."""

    normalized_query = normalized_query or normalize_query(query)
    answer = answer or ""
    query_norm = _norm(query)
    answer_norm = _norm(answer)
    issues: list[AnswerQualityIssue] = []
    required: list[str] = []
    detected: list[str] = []
    contradictions: list[str] = []
    safety_warnings: list[str] = []

    _check_bp_antibiotic(query_norm, answer_norm, issues, required, detected, contradictions)
    _check_clindamycin_retinoid(query_norm, answer_norm, issues, required, detected, contradictions)
    _check_adapalene_antibiotic(query_norm, answer_norm, issues, required, detected, contradictions)
    _check_dalacin_identity(query_norm, answer_norm, issues, required, detected, contradictions)
    _check_epiduo_ingredients(query_norm, answer_norm, issues, required, detected, contradictions)
    _check_differin_class(query_norm, answer_norm, issues, required, detected, contradictions)
    _check_topical_antibiotic_caution(query_norm, answer_norm, issues, safety_warnings)
    _check_retinoid_pregnancy_safety(query_norm, answer_norm, issues, contradictions, safety_warnings)
    _check_isotretinoin_safety(answer_norm, issues, contradictions, safety_warnings)
    _check_acne_type_answer(query_norm, answer_norm, issues, required, detected)

    missing = [fact for fact in _dedupe(required) if fact not in _dedupe(detected)]
    for fact in missing:
        if _required_fact_is_important(fact, normalized_query.intent):
            issues.append(
                AnswerQualityIssue(
                    code="missing_required_fact",
                    severity=WARNING,
                    message=f"Answer may be missing required fact: {fact}.",
                    evidence={"fact": fact},
                    suggested_fix=f"Include: {fact}.",
                )
            )

    has_error = any(issue.severity in {ERROR, CRITICAL} for issue in issues)
    return AnswerVerificationReport(
        passed=not has_error,
        original_query=query,
        intent=normalized_query.intent,
        checked_answer=answer,
        issues=issues,
        required_facts=_dedupe(required),
        detected_facts=_dedupe(detected),
        missing_facts=missing,
        contradictions=_dedupe(contradictions),
        safety_warnings=_dedupe(safety_warnings),
        metadata={
            "packed_context_items": len(packed_context.items) if packed_context else 0,
            "retrieval_trace_available": retrieval_trace is not None,
            "normalized_entities": {
                "drug_product": normalized_query.drug_product,
                "active_ingredient": normalized_query.active_ingredient,
                "drug_class": normalized_query.drug_class,
                "condition": normalized_query.condition,
            },
        },
    )


def apply_answer_guard(
    query: str,
    answer: str,
    normalized_query: NormalizedQuery | None = None,
    packed_context: PackedContext | None = None,
    retrieval_trace: RetrievalTrace | None = None,
    mode: str = "metadata_only",
) -> AnswerGuardResult:
    """Apply answer guard in metadata-only, append-warnings, or strict-safe mode."""

    report = verify_answer_quality(
        query=query,
        answer=answer,
        normalized_query=normalized_query,
        packed_context=packed_context,
        retrieval_trace=retrieval_trace,
    )
    mode = (mode or "metadata_only").strip().lower()
    if mode == "metadata_only":
        return AnswerGuardResult(
            answer=answer,
            original_answer=answer,
            report=report,
            modified=False,
        )

    if mode == "append_warnings" and report.issues:
        warning_text = _short_warning(report)
        if warning_text and warning_text not in answer:
            return AnswerGuardResult(
                answer=answer.rstrip() + "\n\n**Lưu ý an toàn**\n" + warning_text,
                original_answer=answer,
                report=report,
                modified=True,
                modification_reason="appended_quality_warning",
            )

    if mode == "strict_safe" and any(issue.severity == CRITICAL for issue in report.issues):
        return AnswerGuardResult(
            answer=_strict_safe_answer(query, report),
            original_answer=answer,
            report=report,
            modified=True,
            modification_reason="critical_quality_contradiction",
        )

    return AnswerGuardResult(
        answer=answer,
        original_answer=answer,
        report=report,
        modified=False,
    )


def _check_bp_antibiotic(
    query: str,
    answer: str,
    issues: list[AnswerQualityIssue],
    required: list[str],
    detected: list[str],
    contradictions: list[str],
) -> None:
    if not ("benzoyl peroxide" in query or "bpo" in query or re.search(r"\bbp\b", query)):
        return
    if "khang sinh" not in query and "antibiotic" not in query:
        return
    required.append("benzoyl peroxide is not an antibiotic")
    if _contains_any(answer, ["khong phai khang sinh", "not an antibiotic", "khong la khang sinh"]):
        detected.append("benzoyl peroxide is not an antibiotic")
    if _contains_any(answer, ["benzoyl peroxide la khang sinh", "bpo la khang sinh", "benzoyl peroxide is an antibiotic"]):
        contradictions.append("benzoyl peroxide incorrectly described as antibiotic")
        issues.append(_issue("bp_antibiotic_contradiction", CRITICAL, "Benzoyl peroxide was described as an antibiotic."))
    elif "benzoyl peroxide" not in answer and "bpo" not in answer:
        issues.append(_issue("bp_missing_direct_entity", ERROR, "Answer does not directly address benzoyl peroxide."))
    elif "benzoyl peroxide is not an antibiotic" not in detected:
        issues.append(_issue("bp_missing_not_antibiotic", ERROR, "Answer should say benzoyl peroxide is not an antibiotic."))


def _check_clindamycin_retinoid(query: str, answer: str, issues: list[AnswerQualityIssue], required: list[str], detected: list[str], contradictions: list[str]) -> None:
    if "clindamycin" not in query or "retinoid" not in query:
        return
    required.extend(["clindamycin is not a retinoid", "clindamycin is a topical antibiotic"])
    if _contains_any(answer, ["khong phai retinoid", "not a retinoid"]):
        detected.append("clindamycin is not a retinoid")
    if _contains_any(answer, ["khang sinh boi", "topical antibiotic", "topical_antibiotic"]):
        detected.append("clindamycin is a topical antibiotic")
    if _contains_any(answer, ["clindamycin la retinoid", "clindamycin is a retinoid"]):
        contradictions.append("clindamycin incorrectly described as retinoid")
        issues.append(_issue("clindamycin_retinoid_contradiction", CRITICAL, "Clindamycin was described as a retinoid."))


def _check_adapalene_antibiotic(query: str, answer: str, issues: list[AnswerQualityIssue], required: list[str], detected: list[str], contradictions: list[str]) -> None:
    if "adapalene" not in query or ("khang sinh" not in query and "antibiotic" not in query):
        return
    required.extend(["adapalene is not an antibiotic", "adapalene is a topical retinoid"])
    if _contains_any(answer, ["khong phai khang sinh", "not an antibiotic"]):
        detected.append("adapalene is not an antibiotic")
    if _contains_any(answer, ["retinoid boi", "topical retinoid", "topical_retinoid"]):
        detected.append("adapalene is a topical retinoid")
    if _contains_any(answer, ["adapalene la khang sinh", "adapalene la antibiotic", "adapalene is an antibiotic"]):
        contradictions.append("adapalene incorrectly described as antibiotic")
        issues.append(_issue("adapalene_antibiotic_contradiction", CRITICAL, "Adapalene was described as an antibiotic."))


def _check_dalacin_identity(query: str, answer: str, issues: list[AnswerQualityIssue], required: list[str], detected: list[str], contradictions: list[str]) -> None:
    if "dalacin" not in query:
        return
    required.extend(["Dalacin T contains clindamycin", "Dalacin T is a topical antibiotic"])
    if "clindamycin" in answer:
        detected.append("Dalacin T contains clindamycin")
    if _contains_any(answer, ["khang sinh boi", "topical antibiotic", "topical_antibiotic"]):
        detected.append("Dalacin T is a topical antibiotic")
    if _contains_any(answer, ["dalacin t la retinoid", "dalacin la retinoid", "dalacin t is a retinoid"]):
        contradictions.append("Dalacin T incorrectly described as retinoid")
        issues.append(_issue("dalacin_retinoid_contradiction", CRITICAL, "Dalacin T was described as a retinoid."))


def _check_epiduo_ingredients(query: str, answer: str, issues: list[AnswerQualityIssue], required: list[str], detected: list[str], contradictions: list[str]) -> None:
    if "epiduo" not in query:
        return
    if not _contains_any(query, ["bpo", "thanh phan", "co benzoyl", "co bpo", "ingredient"]):
        return
    required.extend(["Epiduo contains adapalene", "Epiduo contains benzoyl peroxide"])
    if "adapalene" in answer:
        detected.append("Epiduo contains adapalene")
    if "benzoyl peroxide" in answer or "bpo" in answer:
        detected.append("Epiduo contains benzoyl peroxide")
    if _contains_any(answer, ["benzoyl peroxide la khang sinh", "benzoyl peroxide is an antibiotic"]):
        contradictions.append("benzoyl peroxide incorrectly described as antibiotic")
        issues.append(_issue("epiduo_bp_antibiotic_contradiction", CRITICAL, "Epiduo answer calls benzoyl peroxide an antibiotic."))
    if ("adapalene" in answer) ^ ("benzoyl peroxide" in answer or "bpo" in answer):
        issues.append(_issue("epiduo_incomplete_ingredients", WARNING, "Epiduo ingredient answer mentions only one key ingredient."))


def _check_differin_class(query: str, answer: str, issues: list[AnswerQualityIssue], required: list[str], detected: list[str], contradictions: list[str]) -> None:
    if "differin" not in query:
        return
    required.extend(["Differin contains adapalene", "Differin is a topical retinoid"])
    if "adapalene" in answer:
        detected.append("Differin contains adapalene")
    if _contains_any(answer, ["retinoid boi", "topical retinoid", "topical_retinoid"]):
        detected.append("Differin is a topical retinoid")
    if _contains_any(answer, ["differin la khang sinh", "differin is an antibiotic"]):
        contradictions.append("Differin incorrectly described as antibiotic")
        issues.append(_issue("differin_antibiotic_contradiction", CRITICAL, "Differin was described as an antibiotic."))


def _check_topical_antibiotic_caution(query: str, answer: str, issues: list[AnswerQualityIssue], safety_warnings: list[str]) -> None:
    mentions_topical_antibiotic = _contains_any(answer, ["khang sinh boi", "topical antibiotic", "clindamycin", "erythromycin"])
    recommends = _contains_any(answer, ["nen dung", "co the dung", "su dung", "dung clindamycin", "apply", "use"])
    has_caution = _contains_any(answer, ["khong nen dung don doc", "khong dung don doc", "khong nen keo dai", "khong dung keo dai", "giam nguy co khang khang sinh", "antibiotic resistance"])
    if mentions_topical_antibiotic and recommends and not has_caution:
        safety_warnings.append("topical antibiotic caution missing")
        issues.append(_issue("topical_antibiotic_caution_missing", WARNING, "Topical antibiotic recommendation should caution against monotherapy or prolonged use."))


def _check_retinoid_pregnancy_safety(query: str, answer: str, issues: list[AnswerQualityIssue], contradictions: list[str], safety_warnings: list[str]) -> None:
    pregnancy_context = _contains_any(query + " " + answer, ["mang thai", "thai ky", "co thai", "pregnancy", "pregnant", "cho con bu"])
    mentions_retinoid = _contains_any(answer, ["retinoid", "adapalene", "tretinoin", "isotretinoin"])
    if not (pregnancy_context and mentions_retinoid):
        return
    has_doctor_caution = _contains_any(answer, ["hoi bac si", "bac si", "doctor", "dermatologist", "da lieu", "san khoa", "khong nen tu dung"])
    if has_doctor_caution:
        safety_warnings.append("retinoid pregnancy doctor caution present")
    else:
        issues.append(_issue("retinoid_pregnancy_caution_missing", ERROR, "Retinoid pregnancy/breastfeeding context should advise clinician review."))
    if _contains_any(answer, ["nen dung retinoid khi mang thai", "co the dung retinoid khi mang thai", "safe during pregnancy", "an toan khi mang thai"]):
        contradictions.append("retinoid recommended as safe in pregnancy")
        issues.append(_issue("retinoid_pregnancy_unsafe", CRITICAL, "Answer recommends retinoid use in pregnancy too confidently."))


def _check_isotretinoin_safety(answer: str, issues: list[AnswerQualityIssue], contradictions: list[str], safety_warnings: list[str]) -> None:
    if "isotretinoin" not in answer:
        return
    has_doctor = _contains_any(answer, ["bac si", "doctor", "dermatologist", "da lieu", "chi dinh", "theo doi", "ke don"])
    if has_doctor:
        safety_warnings.append("isotretinoin clinician supervision present")
    else:
        issues.append(_issue("isotretinoin_supervision_missing", ERROR, "Isotretinoin mention should include clinician supervision."))
    if _contains_any(answer, ["tu dung isotretinoin", "tu uong isotretinoin", "self-use isotretinoin", "take isotretinoin yourself"]):
        contradictions.append("isotretinoin self-use recommended")
        issues.append(_issue("isotretinoin_self_use", CRITICAL, "Answer recommends self-use of isotretinoin."))


def _check_acne_type_answer(query: str, answer: str, issues: list[AnswerQualityIssue], required: list[str], detected: list[str]) -> None:
    acne_type_query = _contains_any(query, ["mun dau den", "blackhead", "mun viem", "inflamed acne", "inflammatory acne"])
    if not acne_type_query:
        return
    required.append("answer addresses acne type")
    lesion_terms = ["mun dau den", "blackhead", "comedone", "nhan mo", "mun viem", "viem", "sang thuong", "inflammatory"]
    if _contains_any(answer, lesion_terms):
        detected.append("answer addresses acne type")
    drug_mentions = sum(1 for term in ["dalacin", "epiduo", "differin", "clindamycin", "adapalene", "benzoyl peroxide"] if term in answer)
    lesion_specific_mentions = sum(1 for term in lesion_terms + ["acne type", "lesion type"] if term in answer)
    if drug_mentions >= 2 and lesion_specific_mentions == 0:
        issues.append(_issue("acne_type_drug_only_answer", ERROR, "Acne type answer appears drug-only and does not address the lesion type."))
    elif drug_mentions >= 2 and "answer addresses acne type" not in detected:
        issues.append(_issue("acne_type_overfocused_on_drugs", WARNING, "Acne type answer may be over-focused on named drugs."))


def _issue(code: str, severity: str, message: str, evidence: dict[str, Any] | None = None, suggested_fix: str | None = None) -> AnswerQualityIssue:
    return AnswerQualityIssue(
        code=code,
        severity=severity,  # type: ignore[arg-type]
        message=message,
        evidence=evidence or {},
        suggested_fix=suggested_fix,
    )


def _short_warning(report: AnswerVerificationReport) -> str:
    critical_or_error = [issue for issue in report.issues if issue.severity in {CRITICAL, ERROR}]
    if critical_or_error:
        return "Câu trả lời cần được kiểm tra lại vì có thể thiếu hoặc mâu thuẫn với thông tin an toàn quan trọng."
    if report.safety_warnings or report.issues:
        return "Không tự dùng thuốc kê đơn hoặc hoạt chất nguy cơ cao; nên hỏi bác sĩ da liễu nếu cần điều trị thuốc."
    return ""


def _strict_safe_answer(query: str, report: AnswerVerificationReport) -> str:
    facts = report.required_facts[:3] or ["Cần kiểm tra lại thông tin y khoa trước khi trả lời."]
    return (
        "**Tóm tắt ngắn**\n"
        "Tôi cần hiệu chỉnh câu trả lời vì phát hiện mâu thuẫn y khoa quan trọng.\n\n"
        "**Thông tin an toàn cần giữ**\n"
        + "\n".join(f"- {fact}" for fact in facts)
        + "\n\n**Lưu ý**\n"
        "Thông tin này chỉ mang tính tham khảo và không thay thế tư vấn của bác sĩ da liễu."
    )


def _required_fact_is_important(fact: str, intent: str | None) -> bool:
    if intent in {"drug_identity", "ingredient_question", "class_check"}:
        return True
    return any(term in fact for term in ["not an antibiotic", "not a retinoid", "acne type"])


def _contains_any(text: str, needles: list[str]) -> bool:
    return any(needle in text for needle in needles)


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFD", text or "")
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    text = text.replace("đ", "d").replace("Đ", "D")
    text = re.sub(r"\s+", " ", text.lower()).strip()
    return text


__all__ = ["apply_answer_guard", "verify_answer_quality"]
