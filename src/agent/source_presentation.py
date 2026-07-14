"""Human-friendly source labels while preserving raw traceability IDs."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


ENTITY_SOURCE_DISPLAY_NAMES = {
    "entity:active_ingredient": "Cơ sở tri thức hoạt chất",
    "entity:drug_product": "Cơ sở tri thức sản phẩm thuốc",
    "entity:drug_class": "Cơ sở tri thức nhóm thuốc",
    "entity:condition": "Cơ sở tri thức tình trạng da",
    "entity:entity": "Cơ sở tri thức nội bộ",
}

FILE_SOURCE_DISPLAY_NAMES = {
    "web_raw_dataset.json": "Bộ dữ liệu kiến thức mụn",
    "PIIS0190962223033893.pdf": "Tài liệu chuyên môn về điều trị mụn",
    "acne-vulgaris-management-pdf-66142088866501.pdf": "Hướng dẫn quản lý mụn trứng cá",
    "qd_4416_cut.pdf": "Tài liệu tiếng Việt về mụn trứng cá",
}

SOURCE_TYPE_ORDER = {
    "entity": 0,
    "document": 1,
    "dataset": 1,
    "other": 2,
}


def build_source_metadata(
    sources: list[Any] | None,
    contexts: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return stable display metadata for retrieved sources.

    ``source_id`` keeps the raw backend identifier for debugging and
    traceability; ``display_name`` is the only field the UI should show.
    """

    context_by_id: dict[str, dict[str, Any]] = {}
    for ctx in contexts or []:
        source_id = _source_id_from_context(ctx)
        if source_id and source_id not in context_by_id:
            context_by_id[source_id] = ctx

    ordered_ids: list[str] = []
    for source in sources or []:
        source_id = _source_id_from_value(source)
        if source_id and source_id not in ordered_ids:
            ordered_ids.append(source_id)
    for source_id in context_by_id:
        if source_id not in ordered_ids:
            ordered_ids.append(source_id)

    entries = [_source_entry(source_id, context_by_id.get(source_id, {})) for source_id in ordered_ids]
    entries.sort(key=lambda item: (SOURCE_TYPE_ORDER.get(item["source_type"], 99), item["display_name"].casefold(), item["source_id"]))
    return entries


def display_names_for_sources(
    sources: list[Any] | None,
    contexts: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Compatibility helper for legacy ``sources: list[str]`` responses."""

    return [entry["display_name"] for entry in build_source_metadata(sources, contexts)]


def _source_entry(source_id: str, context: dict[str, Any]) -> dict[str, Any]:
    document_title = _first_text(
        context.get("document_title"),
        context.get("title"),
        context.get("source_title"),
        _metadata_value(context, "document_title"),
        _metadata_value(context, "title"),
    )
    source_type = _source_type(source_id, context)
    source_path = _first_text(context.get("source_path"), _metadata_value(context, "source_path"))
    display_name = _display_name(source_id, document_title=document_title, source_type=source_type)
    return {
        "source_id": source_id,
        "source_type": source_type,
        "source_path": source_path,
        "document_title": document_title,
        "display_name": display_name,
    }


def _display_name(source_id: str, *, document_title: str | None, source_type: str) -> str:
    if source_id in ENTITY_SOURCE_DISPLAY_NAMES:
        return ENTITY_SOURCE_DISPLAY_NAMES[source_id]
    filename = Path(source_id.replace("\\", "/")).name
    if filename in FILE_SOURCE_DISPLAY_NAMES:
        return FILE_SOURCE_DISPLAY_NAMES[filename]
    if document_title:
        return document_title
    if filename:
        stem = Path(filename).stem
        label = re.sub(r"[_-]+", " ", stem).strip()
        label = re.sub(r"\s+", " ", label)
        if label:
            return label.title()
    if source_type == "entity":
        return "Cơ sở tri thức nội bộ"
    return "Nguồn kiến thức nội bộ"


def _source_id_from_context(context: dict[str, Any]) -> str:
    return _first_text(
        context.get("source_file"),
        context.get("source_id"),
        context.get("source_path"),
        _metadata_value(context, "source_file"),
        _metadata_value(context, "source_id"),
        _metadata_value(context, "source_path"),
    ) or ""


def _source_id_from_value(source: Any) -> str:
    if isinstance(source, dict):
        return _first_text(source.get("source_id"), source.get("source_file"), source.get("source_path"), source.get("display_name")) or ""
    return str(source or "").strip()


def _source_type(source_id: str, context: dict[str, Any]) -> str:
    explicit = _first_text(context.get("source_type"), _metadata_value(context, "source_type"))
    if explicit:
        if explicit == "web_json":
            return "dataset"
        if explicit in {"entity", "document", "dataset", "other"}:
            return explicit
    if source_id.startswith("entity:"):
        return "entity"
    if Path(source_id.replace("\\", "/")).suffix:
        return "document"
    return "other"


def _metadata_value(context: dict[str, Any], key: str) -> Any:
    metadata = context.get("metadata")
    if isinstance(metadata, dict):
        return metadata.get(key)
    return None


def _first_text(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


__all__ = ["build_source_metadata", "display_names_for_sources"]
