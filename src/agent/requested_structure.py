"""Parse user-requested answer structure without calling an LLM."""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from typing import Literal


SemanticIntent = Literal["unknown", "signs_symptoms", "causes_behaviors", "treatment_summary"]


@dataclass(frozen=True)
class RequestedStructure:
    wants_table: bool = False
    required_columns: tuple[str, ...] = ()
    required_rows: tuple[str, ...] = ()
    exact_column_count: int | None = None
    exact_item_count: int | None = None
    style_constraints: tuple[str, ...] = ()
    semantic_intent: SemanticIntent = "unknown"

    @property
    def has_constraints(self) -> bool:
        return bool(
            self.wants_table
            or self.required_columns
            or self.required_rows
            or self.exact_column_count
            or self.exact_item_count
            or self.style_constraints
            or self.semantic_intent != "unknown"
        )


_NUMBER_WORDS = {
    "mot": 1,
    "một": 1,
    "hai": 2,
    "ba": 3,
    "bon": 4,
    "bốn": 4,
    "tu": 4,
    "tư": 4,
    "nam": 5,
    "năm": 5,
    "sau": 6,
    "sáu": 6,
    "bay": 7,
    "bảy": 7,
    "tam": 8,
    "tám": 8,
    "chin": 9,
    "chín": 9,
    "muoi": 10,
    "mười": 10,
}

_COLUMN_SYNONYMS = {
    "thuoc": "thuoc",
    "ten thuoc": "thuoc",
    "lua chon dieu tri": "thuoc",
    "lua chon": "thuoc",
    "hoat chat": "hoat chat",
    "thanh phan": "hoat chat",
    "duong dung": "duong dung",
    "dang dung": "duong dung",
    "cach dung": "duong dung",
    "uu diem": "uu diem",
    "loi ich": "uu diem",
    "diem manh": "uu diem",
    "vai tro chinh": "vai tro chinh",
    "vai tro": "vai tro chinh",
    "tac dung phu thuong gap": "tac dung phu thuong gap",
    "tac dung phu": "tac dung phu thuong gap",
    "luu y su dung": "luu y su dung",
    "luu y an toan": "luu y an toan",
    "canh bao": "luu y an toan",
}

_ENTITY_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("adapalene", ("adapalene", "adapalen", "differin")),
    ("benzoyl peroxide", ("benzoyl peroxide", "benzoyl peroxid", "bpo", " bp ")),
    ("salicylic acid", ("salicylic acid", "acid salicylic", "salicylic", "bha")),
    ("azelaic acid", ("azelaic acid", "azelaic")),
    ("clindamycin", ("clindamycin", "dalacin")),
    ("erythromycin", ("erythromycin", "erythromycin")),
    ("tretinoin", ("tretinoin",)),
    ("tazarotene", ("tazarotene", "tazaroten", "tazorac")),
    ("isotretinoin", ("isotretinoin",)),
    ("doxycycline", ("doxycycline", "doxycyclin")),
    ("Epiduo", ("epiduo",)),
    ("Differin", ("differin",)),
    ("Tazorac", ("tazorac",)),
)


def parse_requested_structure(question: str) -> RequestedStructure:
    """Infer table/list/style constraints from a Vietnamese or English question."""

    raw = question or ""
    text = _accentless(raw)
    padded = f" {text} "
    wants_table = _contains_any(text, ["bang", "table"])
    columns, exact_column_count = _extract_columns(text, wants_table=wants_table)
    rows = _extract_required_rows(text)
    exact_item_count = _extract_exact_item_count(text)
    style_constraints = _extract_style_constraints(text)
    semantic_intent = _infer_semantic_intent(text)

    if wants_table and exact_column_count is None and columns:
        exact_column_count = _extract_number_before_unit(padded, "cot")

    return RequestedStructure(
        wants_table=wants_table,
        required_columns=tuple(columns),
        required_rows=tuple(rows),
        exact_column_count=exact_column_count,
        exact_item_count=exact_item_count,
        style_constraints=tuple(style_constraints),
        semantic_intent=semantic_intent,
    )


def canonical_column_name(column: str) -> str:
    normalized = _clean_item(column)
    return _COLUMN_SYNONYMS.get(normalized, normalized)


def _extract_columns(text: str, *, wants_table: bool) -> tuple[list[str], int | None]:
    if not wants_table:
        return [], None

    patterns = [
        r"(?:dung\s+)?(?P<count>\d+|mot|hai|ba|bon|tu|nam|sau|bay|tam|chin|muoi)\s+cot\s*(?:la|:)?\s*(?P<cols>.+)",
        r"(?:voi|với)?\s*(?:dung\s+)?(?P<count>\d+|mot|hai|ba|bon|tu|nam|sau|bay|tam|chin|muoi)\s+cot\s*(?:la|:)?\s*(?P<cols>.+)",
        r"\bgom\b\s*(?:(?P<count>\d+|mot|hai|ba|bon|tu|nam|sau|bay|tam|chin|muoi)\s+cot\s*(?:la)?\s*)?(?P<cols>.+)",
        r"\bbao gom\b\s*(?:(?P<count>\d+|mot|hai|ba|bon|tu|nam|sau|bay|tam|chin|muoi)\s+cot\s*(?:la)?\s*)?(?P<cols>.+)",
        r"\btheo cac tieu chi\b\s*(?P<cols>.+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        segment = _truncate_column_segment(match.group("cols"))
        columns = _split_items(segment)
        count = _parse_number(match.groupdict().get("count"))
        if columns:
            return [canonical_column_name(item) for item in columns], count
    return [], _extract_number_before_unit(f" {text} ", "cot")


def _truncate_column_segment(segment: str) -> str:
    segment = segment.strip(" .?!;:")
    stop_patterns = [
        r"\s+cho\s+(?:adapalene|benzoyl|salicylic|clindamycin|epiduo|differin|tazorac|mun\s)",
        r"\s+ve\s+(?:adapalene|benzoyl|salicylic|clindamycin|epiduo|differin|tazorac|mun\s)",
        r"\s+trong\s+\d+\s+tuan",
        r"\s+nhung\s+",
        r"\s+va\s+khong\s+",
    ]
    cut = len(segment)
    for pattern in stop_patterns:
        match = re.search(pattern, segment)
        if match:
            cut = min(cut, match.start())
    return segment[:cut].strip(" .?!;:")


def _split_items(segment: str) -> list[str]:
    cleaned = re.sub(r"\b(cac|nhung|cot|muc|dimension|dimensions|la)\b", " ", segment)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .?!;:")
    cleaned = re.sub(r"\s+(?:va|và)\s+", ", ", cleaned)
    output: list[str] = []
    for raw in cleaned.split(","):
        item = _clean_item(raw)
        if 2 <= len(item) <= 48:
            output.append(item)
    return _dedupe(output)


def _extract_required_rows(text: str) -> list[str]:
    rows: list[str] = []
    for label, aliases in _ENTITY_ALIASES:
        if any(_entity_alias_present(text, alias) for alias in aliases):
            rows.append(label)

    if _contains_any(text, ["mun nhe trung binh", "mun nhe-trung binh", "mun nhe den trung binh"]):
        rows.append("mụn nhẹ-trung bình")
    if _contains_any(text, ["mun trung binh nang", "mun trung binh-nang", "mun trung binh den nang"]):
        rows.append("mụn trung bình-nặng")
    return _dedupe(rows)


def _extract_exact_item_count(text: str) -> int | None:
    patterns = [
        r"(?:liet ke|nêu|neu|dua ra|cho toi|cho tôi)\s+(?:dung\s+)?(?P<count>\d+|mot|hai|ba|bon|tu|nam|sau|bay|tam|chin|muoi)\s+(?:dau hieu|trieu chung|bieu hien|y|muc|bullet|nguyen nhan|thoi quen)",
        r"(?:dung\s+)?(?P<count>\d+|mot|hai|ba|bon|tu|nam|sau|bay|tam|chin|muoi)\s+(?:dau hieu|trieu chung|bieu hien|y|muc|bullet|nguyen nhan|thoi quen)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return _parse_number(match.group("count"))
    return None


def _extract_style_constraints(text: str) -> list[str]:
    constraints: list[str] = []
    if _contains_any(text, ["tieu de dam", "in dam", "bold", "chu dam"]):
        constraints.append("bold_headings")
    if _contains_any(text, ["khong dung bang", "khong bang"]):
        constraints.append("avoid_table")
    return constraints


def _infer_semantic_intent(text: str) -> SemanticIntent:
    if _contains_any(text, ["dau hieu", "trieu chung", "bieu hien", "nhan biet"]):
        return "signs_symptoms"
    if _contains_any(text, ["nguyen nhan", "thoi quen", "lam nang", "trigger", "yeu to"]):
        return "causes_behaviors"
    if _contains_any(text, ["lua chon dieu tri", "dieu tri dau tay", "phac do", "12 tuan"]):
        return "treatment_summary"
    return "unknown"


def _extract_number_before_unit(text: str, unit: str) -> int | None:
    match = re.search(rf"\b(?P<count>\d+|mot|hai|ba|bon|tu|nam|sau|bay|tam|chin|muoi)\s+{unit}\b", text)
    if not match:
        return None
    return _parse_number(match.group("count"))


def _parse_number(value: str | None) -> int | None:
    if not value:
        return None
    value = value.strip().lower()
    if value.isdigit():
        return int(value)
    return _NUMBER_WORDS.get(value)


def _entity_alias_present(text: str, alias: str) -> bool:
    alias_norm = _clean_item(alias)
    if not alias_norm:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(alias_norm)}(?![a-z0-9])", f" {text} ") is not None


def _contains_any(text: str, needles: list[str]) -> bool:
    return any(needle in text for needle in needles)


def _clean_item(value: str) -> str:
    value = value.replace("_", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip(" .?!;:-").lower()


def _accentless(text: str) -> str:
    value = unicodedata.normalize("NFKC", text or "")
    value = value.replace("đ", "d").replace("Đ", "D")
    value = "".join(
        char for char in unicodedata.normalize("NFD", value)
        if unicodedata.category(char) != "Mn"
    )
    value = value.lower()
    value = value.translate(str.maketrans({"—": "-", "–": "-", "−": "-", "(": " ", ")": " ", "/": " "}))
    return re.sub(r"\s+", " ", value).strip()


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


__all__ = ["RequestedStructure", "canonical_column_name", "parse_requested_structure"]
