"""
Text encoding helpers for repairing common UTF-8 mojibake.
"""

from __future__ import annotations

MOJIBAKE_MARKERS = ("Ã", "Ä", "á»", "áº", "Æ", "Â", "Ð")

LOSSY_MOJIBAKE_REPLACEMENTS = {
    "Äiá»u trá»": "Điều trị",
    "Äiá»u": "Điều",
    "ÄÆ¡n": "đơn",
    "sÄ©": "sĩ",
    "bÃ¡c": "bác",
    "khÃ´ng": "không",
    "kÃª": "kê",
    "liá»…u": "liễu",
}


def looks_like_mojibake(value: str) -> bool:
    """Return True when a string contains common UTF-8-as-latin/cp1252 markers."""
    return isinstance(value, str) and any(marker in value for marker in MOJIBAKE_MARKERS)


def repair_mojibake(value: str) -> str:
    """Repair UTF-8 text that was accidentally decoded as latin-1/cp1252."""
    if not isinstance(value, str) or not value or not looks_like_mojibake(value):
        return value

    original_score = sum(marker in value for marker in MOJIBAKE_MARKERS)
    for encoding in ("latin1", "cp1252"):
        try:
            repaired = value.encode(encoding).decode("utf-8")
        except UnicodeError:
            continue
        if repaired and sum(marker in repaired for marker in MOJIBAKE_MARKERS) < original_score:
            return repaired

    repaired = value
    for broken, fixed in LOSSY_MOJIBAKE_REPLACEMENTS.items():
        repaired = repaired.replace(broken, fixed)
    if repaired != value:
        return repaired

    return value
