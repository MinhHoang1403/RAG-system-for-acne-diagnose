"""
tests/test_ingest_chunking.py – Chunking logic unit tests
"""

from __future__ import annotations

import pytest

# Import chunking helpers directly (no DB / vector store required)
from scripts.ingest_knowledge import SemanticChunk, chunk_markdown_text


def test_chunk_markdown_splits_large_section():
    text = "# Acne\n\n" + ("acne treatment guidance " * 200)
    chunks = chunk_markdown_text(text, source_file="test.md", max_section_chars=200)
    assert len(chunks) > 1
    assert all(isinstance(chunk, SemanticChunk) for chunk in chunks)
    assert all(chunk.source_file == "test.md" for chunk in chunks)


def test_chunk_markdown_filters_empty():
    chunks = chunk_markdown_text("   \n   \n   ", source_file="empty.md")
    # All-whitespace content should produce no chunks
    assert chunks == []


def test_chunk_markdown_assigns_index():
    chunks = chunk_markdown_text(
        "# Acne\n\n" + ("word " * 500),
        source_file="test.md",
        max_section_chars=200,
    )
    for i, chunk in enumerate(chunks):
        assert chunk.chunk_index == i


def test_semantic_chunk_hash_stable():
    content = "Hello, acne research world!"
    chunk1 = SemanticChunk(source_file="test.md", chunk_index=0, text=content)
    chunk2 = SemanticChunk(source_file="test.md", chunk_index=0, text=content)
    assert chunk1.content_hash == chunk2.content_hash
    assert chunk1.chunk_id == chunk2.chunk_id
