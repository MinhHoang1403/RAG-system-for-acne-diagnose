from scripts.ingest_knowledge import discover_knowledge_files, discover_source_documents


def test_discover_knowledge_files_includes_pdf_docx_and_json(tmp_path) -> None:
    pdf = tmp_path / "guide.pdf"
    docx = tmp_path / "notes.docx"
    json_file = tmp_path / "web_raw_dataset.json"
    ignored = tmp_path / "ignore.txt"
    for path in (pdf, docx, json_file, ignored):
        path.write_text("x", encoding="utf-8")

    discovered = {path.name for path in discover_knowledge_files(tmp_path)}

    assert {"guide.pdf", "notes.docx", "web_raw_dataset.json"} <= discovered
    assert "ignore.txt" not in discovered
    assert discovered == {path.name for path in discover_source_documents(tmp_path)}
