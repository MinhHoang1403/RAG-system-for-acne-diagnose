"""Clause-scoped deterministic proposition detection for Vietnamese answers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Literal

from src.quality.contracts import DomainProposition
from src.quality.vietnamese_text import build_matching_views

Relation = Literal[
    "is_a",
    "is_not_a",
    "contains",
    "does_not_contain",
    "requires_supervision",
    "unsafe_recommendation",
    "uncertain",
]


@dataclass(frozen=True)
class EntitySpec:
    canonical: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class PredicateSpec:
    canonical: str
    aliases: tuple[str, ...]


ENTITIES: dict[str, EntitySpec] = {
    "benzoyl_peroxide": EntitySpec("benzoyl_peroxide", ("benzoyl peroxide", "bpo", "bp")),
    "clindamycin": EntitySpec("clindamycin", ("clindamycin", "dalacin t", "dalacin")),
    "adapalene": EntitySpec("adapalene", ("adapalene", "differin")),
    "dalacin_t": EntitySpec("Dalacin T", ("dalacin t", "dalacin")),
    "epiduo": EntitySpec("Epiduo", ("epiduo",)),
    "differin": EntitySpec("Differin", ("differin",)),
}

PREDICATES: dict[str, PredicateSpec] = {
    "antibiotic": PredicateSpec(
        "antibiotic",
        ("kháng sinh", "khang sinh", "antibiotic", "thuốc kháng sinh", "thuoc khang sinh"),
    ),
    "retinoid": PredicateSpec(
        "retinoid",
        ("retinoid", "retinoid bôi", "retinoid boi", "topical retinoid", "topical_retinoid"),
    ),
    "topical_antibiotic": PredicateSpec(
        "topical_antibiotic",
        (
            "kháng sinh bôi",
            "khang sinh boi",
            "kháng sinh bôi tại chỗ",
            "khang sinh boi tai cho",
            "topical antibiotic",
            "topical_antibiotic",
        ),
    ),
    "benzoyl_peroxide": PredicateSpec("benzoyl_peroxide", ("benzoyl peroxide", "bpo", "bp")),
    "adapalene": PredicateSpec("adapalene", ("adapalene",)),
    "clindamycin": PredicateSpec("clindamycin", ("clindamycin",)),
}

_CLAUSE_SPLIT_RE = re.compile(
    r"(?:[.;\n\r]+|\b(?:nhưng|tuy nhiên|còn|trong khi|but|however|whereas)\b)"
)
_QUOTE_RE = re.compile(r'"[^"]+"')

_UNCERTAIN_MARKERS = (
    "khong the khang dinh",
    "chua the khang dinh",
    "khong du de khang dinh",
    "khong chac",
    "chua ro",
    "uncertain",
)
_REPORTED_CLAIM_MARKERS = (
    "mot so nguoi noi",
    "co nguoi noi",
    "nguoi ta noi",
    "noi rang",
    "cho rang",
    "claim",
)
_CLAIM_REJECTION_MARKERS = (
    "dieu do khong dung",
    "dieu nay khong dung",
    "khong dung",
    "sai",
    "khong chinh xac",
)


def detect_entity_mentions(text: str) -> list[str]:
    """Return canonical entity keys mentioned in text."""

    _, accentless = build_matching_views(text)
    mentions: list[str] = []
    for key, spec in ENTITIES.items():
        if _contains_alias(accentless, spec.aliases):
            mentions.append(key)
    return list(dict.fromkeys(mentions))


def detect_negated_relation(
    text: str,
    subject_aliases: list[str],
    predicate_aliases: list[str],
) -> bool:
    """Return True when text contains a clear subject is-not-a predicate relation."""

    return _detect_relation_in_text(text, subject_aliases, predicate_aliases, relation="is_not_a")


def detect_positive_relation(
    text: str,
    subject_aliases: list[str],
    predicate_aliases: list[str],
) -> bool:
    """Return True when text contains a clear subject is-a predicate relation."""

    return _detect_relation_in_text(text, subject_aliases, predicate_aliases, relation="is_a")


def extract_domain_propositions(
    text: str,
    query_context: object | None = None,
) -> list[DomainProposition]:
    """Extract deterministic domain propositions from answer text.

    The detector is intentionally small: it works at clause level, checks
    negated relations before positive relations, and only uses query context to
    resolve subjectless answers when exactly one known subject is present there.
    """

    clauses = _split_clauses(text)
    context_subject = _single_context_subject(query_context)
    quoted_false_claims = _quoted_false_claims(text)
    propositions: list[DomainProposition] = []
    for subject, predicate in quoted_false_claims:
        propositions.append(
            _proposition(
                subject=ENTITIES[subject].canonical,
                relation="is_not_a",
                object_=PREDICATES[predicate].canonical,
                clause=text,
                source_rule="quoted_claim_rejected",
                confidence=0.75,
            )
        )

    for clause in clauses:
        if not clause:
            continue
        _, clause_norm = build_matching_views(clause)
        if _is_uncertain_clause(clause_norm):
            propositions.append(
                _proposition(
                    subject=context_subject or "unknown",
                    relation="uncertain",
                    object_="unknown",
                    clause=clause,
                    source_rule="uncertain_clause",
                    confidence=0.4,
                )
            )
            continue

        subjects = _subjects_for_clause(clause_norm)
        if not subjects and context_subject:
            subjects = [context_subject]

        for subject in subjects:
            for predicate_key, predicate in PREDICATES.items():
                if subject == predicate_key:
                    continue
                if _clause_has_negated_relation(clause_norm, ENTITIES[subject].aliases, predicate.aliases):
                    propositions.append(
                        _proposition(
                            subject=ENTITIES[subject].canonical,
                            relation="is_not_a",
                            object_=predicate.canonical,
                            clause=clause,
                            source_rule="negated_membership",
                        )
                    )
                    continue
                if _is_reported_claim_clause(clause_norm) or _matches_quoted_false_claim(
                    quoted_false_claims,
                    subject,
                    predicate_key,
                ):
                    continue
                if _clause_has_positive_relation(clause_norm, ENTITIES[subject].aliases, predicate.aliases):
                    propositions.append(
                        _proposition(
                            subject=ENTITIES[subject].canonical,
                            relation="is_a",
                            object_=predicate.canonical,
                            clause=clause,
                            source_rule="positive_membership",
                        )
                    )

        propositions.extend(_extract_contains_relations(clause, clause_norm))

    return _dedupe_propositions(propositions)


def proposition_exists(
    propositions: Iterable[DomainProposition],
    *,
    subject: str,
    relation: str,
    object_: str,
) -> bool:
    subject_norm = _normalize_key(subject)
    object_norm = _normalize_key(object_)
    return any(
        _normalize_key(prop.subject) == subject_norm
        and prop.relation == relation
        and _normalize_key(prop.object) == object_norm
        for prop in propositions
    )


def _detect_relation_in_text(
    text: str,
    subject_aliases: list[str],
    predicate_aliases: list[str],
    *,
    relation: Literal["is_a", "is_not_a"],
) -> bool:
    for clause in _split_clauses(text):
        _, clause_norm = build_matching_views(clause)
        if relation == "is_not_a" and _clause_has_negated_relation(
            clause_norm,
            tuple(subject_aliases),
            tuple(predicate_aliases),
        ):
            return True
        if relation == "is_a" and _clause_has_positive_relation(
            clause_norm,
            tuple(subject_aliases),
            tuple(predicate_aliases),
        ):
            return True
    return False


def _split_clauses(text: str) -> list[str]:
    accent_preserving, _ = build_matching_views(text)
    parts = _CLAUSE_SPLIT_RE.split(accent_preserving)
    clauses: list[str] = []
    carry_subject: str | None = None
    for raw in parts:
        clause = raw.strip(" ,")
        if not clause:
            continue
        colon_parts = [part.strip(" ,") for part in re.split(r"[:]+", clause) if part.strip(" ,")]
        if len(colon_parts) > 1:
            for part in colon_parts:
                _, part_norm = build_matching_views(part)
                subjects = _subjects_for_clause(part_norm)
                predicates = _predicate_mentions(part_norm)
                if subjects and not predicates and len(part.split()) <= 4:
                    carry_subject = part
                    continue
                if carry_subject and not subjects:
                    part = f"{carry_subject} {part}"
                clauses.append(part)
                carry_subject = None
            continue
        _, clause_norm = build_matching_views(clause)
        subjects = _subjects_for_clause(clause_norm)
        predicates = _predicate_mentions(clause_norm)
        if subjects and not predicates and len(clause.split()) <= 4:
            carry_subject = clause
            continue
        if carry_subject and not subjects:
            clause = f"{carry_subject} {clause}"
            carry_subject = None
        clauses.append(clause)
    return clauses


def _single_context_subject(query_context: object | None) -> str | None:
    if query_context is None:
        return None
    if isinstance(query_context, str):
        text = query_context
    else:
        text = " ".join(
            str(getattr(query_context, name, "") or "")
            for name in ("drug_product", "active_ingredient", "drug_class", "condition")
        )
        if not text.strip():
            text = str(query_context)
    mentions = [key for key in detect_entity_mentions(text) if key in ENTITIES]
    normalized: list[str] = []
    for key in mentions:
        if key == "dalacin_t":
            normalized.append("clindamycin")
        elif key == "differin":
            normalized.append("adapalene")
        else:
            normalized.append(key)
    unique = list(dict.fromkeys(normalized))
    return unique[0] if len(unique) == 1 else None


def _subjects_for_clause(clause_norm: str) -> list[str]:
    subjects = [key for key, spec in ENTITIES.items() if _contains_alias(clause_norm, spec.aliases)]
    normalized: list[str] = []
    for key in subjects:
        if key == "dalacin_t":
            normalized.append("clindamycin")
        elif key == "differin":
            normalized.append("adapalene")
        else:
            normalized.append(key)
    return list(dict.fromkeys(normalized))


def _predicate_mentions(clause_norm: str) -> list[str]:
    return [key for key, spec in PREDICATES.items() if _contains_alias(clause_norm, spec.aliases)]


def _clause_has_negated_relation(
    clause_norm: str,
    subject_aliases: tuple[str, ...],
    predicate_aliases: tuple[str, ...],
) -> bool:
    if "khong chi la" in clause_norm or "not only" in clause_norm:
        return False
    for subject in subject_aliases:
        subject_pattern = _alias_pattern(subject)
        for predicate in predicate_aliases:
            predicate_pattern = _alias_pattern(predicate)
            filler = r"(?:la\s+)?(?:(?:mot\s+)?loai\s+|mot\s+|nhom\s+|thuoc\s+)?"
            patterns = [
                rf"\b{subject_pattern}\b[\w\s,-]{{0,80}}\bkhong\s+phai\s+{filler}{predicate_pattern}\b",
                rf"\b{subject_pattern}\b[\w\s,-]{{0,80}}\bkhong\s+la\s+(?:mot\s+loai\s+|nhom\s+|thuoc\s+)?{predicate_pattern}\b",
                rf"\b{subject_pattern}\b[\w\s,-]{{0,80}}\bkhong\s+thuoc\s+(?:nhom\s+|loai\s+|dong\s+)?(?:thuoc\s+)?{predicate_pattern}\b",
                rf"\b{subject_pattern}\b[\w\s,-]{{0,80}}\bkhong\s+duoc\s+(?:xem|coi)\s+la\s+(?:mot\s+loai\s+|thuoc\s+)?{predicate_pattern}\b",
                rf"\b{subject_pattern}\b[\w\s,-]{{0,80}}\bkhong\s+duoc\s+xep\s+vao\s+(?:nhom\s+|loai\s+|dong\s+)?(?:thuoc\s+)?{predicate_pattern}\b",
                rf"\b{subject_pattern}\b[\w\s,-]{{0,80}}\bkhong\s+co\s+ban\s+chat\s+la\s+(?:mot\s+loai\s+|thuoc\s+)?{predicate_pattern}\b",
                rf"\b{subject_pattern}\b[\w\s,-]{{0,80}}\bnot\s+(?:an?\s+)?{predicate_pattern}\b",
            ]
            if any(re.search(pattern, clause_norm) for pattern in patterns):
                return True
            subjectless = [
                rf"\bkhong\s+phai\s+{filler}{predicate_pattern}\b",
                rf"\bkhong\s+thuoc\s+(?:nhom\s+|loai\s+|dong\s+)?(?:thuoc\s+)?{predicate_pattern}\b",
            ]
            if not _contains_alias(clause_norm, subject_aliases) and any(
                re.search(pattern, clause_norm) for pattern in subjectless
            ):
                return True
    return False


def _clause_has_positive_relation(
    clause_norm: str,
    subject_aliases: tuple[str, ...],
    predicate_aliases: tuple[str, ...],
) -> bool:
    if _clause_has_negated_relation(clause_norm, subject_aliases, predicate_aliases):
        return False
    for subject in subject_aliases:
        subject_pattern = _alias_pattern(subject)
        for predicate in predicate_aliases:
            predicate_pattern = _alias_pattern(predicate)
            patterns = [
                rf"\b{subject_pattern}\b[\w\s,-]{{0,80}}\bkhong\s+chi\s+la\s+(?:mot\s+loai\s+|mot\s+|thuoc\s+)?{predicate_pattern}\b",
                rf"\b{subject_pattern}\b[\w\s,-]{{0,80}}\bla\s+(?:mot\s+loai\s+|mot\s+|nhom\s+|thuoc\s+)?{predicate_pattern}\b",
                rf"\b{subject_pattern}\b[\w\s,-]{{0,80}}\bthuoc\s+(?:nhom\s+|loai\s+|dong\s+)?(?:thuoc\s+)?{predicate_pattern}\b",
                rf"\b{subject_pattern}\b[\w\s,-]{{0,80}}\bduoc\s+(?:xem|coi)\s+la\s+(?:mot\s+loai\s+|thuoc\s+)?{predicate_pattern}\b",
                rf"\b{subject_pattern}\b[\w\s,-]{{0,80}}\bduoc\s+xep\s+vao\s+(?:nhom\s+|loai\s+|dong\s+)?(?:thuoc\s+)?{predicate_pattern}\b",
                rf"\b{subject_pattern}\b[\w\s,-]{{0,80}}\bco\s+ban\s+chat\s+la\s+(?:mot\s+loai\s+|thuoc\s+)?{predicate_pattern}\b",
                rf"\b{subject_pattern}\b[\w\s,-]{{0,80}}\bis\s+(?:an?\s+)?{predicate_pattern}\b",
            ]
            if any(re.search(pattern, clause_norm) for pattern in patterns):
                return True
    return False


def _extract_contains_relations(clause: str, clause_norm: str) -> list[DomainProposition]:
    propositions: list[DomainProposition] = []
    for product_key in ("epiduo", "dalacin_t", "differin"):
        if not _contains_alias(clause_norm, ENTITIES[product_key].aliases):
            continue
        for ingredient_key in ("adapalene", "benzoyl_peroxide", "clindamycin"):
            if ingredient_key == product_key:
                continue
            if not _contains_alias(clause_norm, PREDICATES[ingredient_key].aliases):
                continue
            if re.search(r"\b(?:chua|co|gom|contains?|thanh phan|hoat chat|ingredient)\b", clause_norm):
                propositions.append(
                    _proposition(
                        subject=ENTITIES[product_key].canonical,
                        relation="contains",
                        object_=PREDICATES[ingredient_key].canonical,
                        clause=clause,
                        source_rule="contains_ingredient",
                    )
                )
    return propositions


def _quoted_false_claims(text: str) -> set[tuple[str, str]]:
    _, text_norm = build_matching_views(text)
    if not any(marker in text_norm for marker in _CLAIM_REJECTION_MARKERS):
        return set()
    quoted_claims: set[tuple[str, str]] = set()
    for quoted in _QUOTE_RE.findall(text_norm):
        for subject in _subjects_for_clause(quoted):
            for predicate in _predicate_mentions(quoted):
                if _clause_has_positive_relation(quoted, ENTITIES[subject].aliases, PREDICATES[predicate].aliases):
                    quoted_claims.add((subject, predicate))
    return quoted_claims


def _matches_quoted_false_claim(
    quoted_false_claims: set[tuple[str, str]],
    subject: str,
    predicate: str,
) -> bool:
    return (subject, predicate) in quoted_false_claims


def _is_uncertain_clause(clause_norm: str) -> bool:
    return any(marker in clause_norm for marker in _UNCERTAIN_MARKERS)


def _is_reported_claim_clause(clause_norm: str) -> bool:
    return any(marker in clause_norm for marker in _REPORTED_CLAIM_MARKERS)


def _contains_alias(text: str, aliases: Iterable[str]) -> bool:
    for alias in aliases:
        _, alias_norm = build_matching_views(alias)
        if re.search(rf"\b{re.escape(alias_norm)}\b", text):
            return True
    return False


def _alias_pattern(alias: str) -> str:
    _, alias_norm = build_matching_views(alias)
    return re.escape(alias_norm).replace(r"\ ", r"\s+")


def _proposition(
    *,
    subject: str,
    relation: Relation,
    object_: str,
    clause: str,
    source_rule: str,
    confidence: float = 0.95,
) -> DomainProposition:
    normalized, accentless = build_matching_views(clause)
    return DomainProposition(
        subject=subject,
        relation=relation,
        object=object_,
        confidence=confidence,
        matched_text=clause.strip(),
        normalized_text=accentless or normalized,
        source_rule=source_rule,
    )


def _dedupe_propositions(propositions: list[DomainProposition]) -> list[DomainProposition]:
    seen: set[tuple[str, str, str, str]] = set()
    deduped: list[DomainProposition] = []
    for proposition in propositions:
        key = (
            _normalize_key(proposition.subject),
            proposition.relation,
            _normalize_key(proposition.object),
            proposition.source_rule,
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(proposition)
    return deduped


def _normalize_key(value: str) -> str:
    _, value_norm = build_matching_views(value)
    return value_norm.replace(" ", "_")


__all__ = [
    "ENTITIES",
    "PREDICATES",
    "detect_entity_mentions",
    "detect_negated_relation",
    "detect_positive_relation",
    "extract_domain_propositions",
    "proposition_exists",
]
