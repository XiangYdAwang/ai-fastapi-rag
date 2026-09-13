from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest
from fastapi import HTTPException

from app.services.document_parser import extract_text_from_bytes


def make_docx_bytes(paragraphs: list[str]) -> bytes:
    namespace = (
        "http://schemas.openxmlformats.org/"
        "wordprocessingml/2006/main"
    )
    paragraph_xml = "".join(
        (
            "<w:p><w:r><w:t>"
            f"{paragraph}"
            "</w:t></w:r></w:p>"
        )
        for paragraph in paragraphs
    )
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{namespace}">'
        f"<w:body>{paragraph_xml}</w:body>"
        "</w:document>"
    )

    output = BytesIO()

    with ZipFile(output, "w") as archive:
        archive.writestr("word/document.xml", document_xml)

    return output.getvalue()


def test_extract_utf8_text() -> None:
    assert extract_text_from_bytes(
        "FastAPI 是一个 Python Web 框架。".encode("utf-8"),
        ".txt",
    ) == "FastAPI 是一个 Python Web 框架。"


def test_reject_invalid_utf8_text() -> None:
    with pytest.raises(HTTPException) as error:
        extract_text_from_bytes(b"\xff\xfe", ".txt")

    assert error.value.status_code == 400


def test_extract_docx_with_standard_library() -> None:
    content = make_docx_bytes(["First paragraph", "Second paragraph"])

    assert extract_text_from_bytes(content, ".docx") == (
        "First paragraph\nSecond paragraph"
    )


def test_extract_existing_pdf_fixture() -> None:
    pdf_path = Path(__file__).parents[1] / "sample.pdf"
    text = extract_text_from_bytes(pdf_path.read_bytes(), ".pdf")

    assert "pgvector" in text


def test_reject_unsupported_format() -> None:
    with pytest.raises(HTTPException) as error:
        extract_text_from_bytes(b"data", ".csv")

    assert error.value.status_code == 415