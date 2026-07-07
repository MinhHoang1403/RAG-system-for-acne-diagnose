"""Deterministic Vietnamese text normalization for answer verification."""

from __future__ import annotations

import re
import unicodedata

_ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\ufeff]")
_MARKDOWN_MARKERS_RE = re.compile(r"(\*\*|__|`)")
_WHITESPACE_RE = re.compile(r"\s+")

_DASH_TRANSLATION = str.maketrans(
    {
        "—": "-",
        "–": "-",
        "−": "-",
        "‐": "-",
        "‑": "-",
    }
)

_PUNCT_TRANSLATION = str.maketrans(
    {
        "“": '"',
        "”": '"',
        "„": '"',
        "«": '"',
        "»": '"',
        "‘": "'",
        "’": "'",
        "‚": "'",
        "(": " ",
        ")": " ",
        "[": " ",
        "]": " ",
        "{": " ",
        "}": " ",
        "/": " ",
        "\\": " ",
    }
)


def normalize_vietnamese_text(text: str) -> str:
    """Return a stable accent-preserving normalized representation."""

    normalized = unicodedata.normalize("NFKC", text or "")
    normalized = _ZERO_WIDTH_RE.sub("", normalized)
    normalized = normalized.translate(_DASH_TRANSLATION)
    normalized = normalized.translate(_PUNCT_TRANSLATION)
    normalized = _MARKDOWN_MARKERS_RE.sub("", normalized)
    normalized = normalized.lower()
    normalized = _WHITESPACE_RE.sub(" ", normalized).strip()
    return normalized


def strip_vietnamese_diacritics(text: str) -> str:
    """Strip Vietnamese diacritics, including explicit đ/Đ handling."""

    text = (text or "").replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return unicodedata.normalize("NFC", stripped)


def build_matching_views(text: str) -> tuple[str, str]:
    """Build accent-preserving and accentless matching views."""

    accent_preserving = normalize_vietnamese_text(text)
    accentless = normalize_vietnamese_text(strip_vietnamese_diacritics(accent_preserving))
    return accent_preserving, accentless


__all__ = [
    "build_matching_views",
    "normalize_vietnamese_text",
    "strip_vietnamese_diacritics",
]
