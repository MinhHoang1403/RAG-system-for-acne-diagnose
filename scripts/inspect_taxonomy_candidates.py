#!/usr/bin/env python3
"""Inspect local files for taxonomy expansion candidates using deterministic keywords."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.knowledge.normalizer import DrugEntityNormalizer  # noqa: E402
from src.knowledge.taxonomy_models import normalize_taxonomy_alias  # noqa: E402


DEFAULT_TERMS = {
    "salicylic acid": "active_ingredient",
    "retinol": "active_ingredient",
    "erythromycin": "active_ingredient",
    "spironolactone": "active_ingredient",
    "tazarotene": "active_ingredient",
    "minocycline": "active_ingredient",
    "dapsone": "active_ingredient",
    "sodium sulfacetamide": "active_ingredient",
    "hormonal therapy": "drug_class",
    "oral contraceptive": "drug_class",
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect local source text for draft taxonomy candidates.")
    parser.add_argument("--source", action="append", default=[], help="Local source path. Can be repeated.")
    parser.add_argument("--max-snippets", type=int, default=3)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    sources = [Path(path) for path in args.source] or [
        PROJECT_ROOT / "sample_data" / "web_raw_dataset.json",
        *(PROJECT_ROOT / "data" / "cache" / "markdown").glob("*.md"),
    ]
    existing = _existing_aliases()
    texts = list(_load_texts(sources))
    candidates: list[dict[str, Any]] = []
    for term, candidate_type in DEFAULT_TERMS.items():
        normalized = normalize_taxonomy_alias(term)
        snippets = []
        source_files = []
        for source_id, text in texts:
            match = re.search(re.escape(term), text, flags=re.IGNORECASE)
            if not match:
                continue
            source_files.append(source_id.split("#", 1)[0])
            start = max(0, match.start() - 80)
            end = min(len(text), match.end() + 120)
            snippet = re.sub(r"\s+", " ", text[start:end]).strip()
            snippets.append(snippet[:280])
            if len(snippets) >= args.max_snippets:
                break
        if not snippets:
            continue
        candidates.append(
            {
                "name": term,
                "candidate_type": candidate_type,
                "source_files": sorted(set(source_files)),
                "evidence_snippets": snippets,
                "existing_entity": normalized in existing,
                "confidence": 0.6 if normalized not in existing else 0.9,
                "recommended_status": "draft" if normalized not in existing else "verified_existing",
            }
        )
    print(json.dumps({"candidates": candidates}, ensure_ascii=False, indent=2))
    return 0


def _existing_aliases() -> set[str]:
    normalizer = DrugEntityNormalizer()
    return set(normalizer.alias_index)


def _load_texts(paths: list[Path]):
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        raw = path.read_text(encoding="utf-8", errors="ignore")
        if path.suffix.lower() == ".json":
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                yield str(path), raw
                continue
            if isinstance(data, list):
                for index, item in enumerate(data):
                    if isinstance(item, dict):
                        yield f"{path}#{index}", str(item.get("raw_text") or "")
                continue
        yield str(path), raw


if __name__ == "__main__":
    raise SystemExit(main())
