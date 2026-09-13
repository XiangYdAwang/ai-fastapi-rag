from io import BytesIO
from xml.etree import ElementTree
from zipfile import ZipFile

from fastapi import HTTPException, status
from pypdf import PdfReader


def extract_text_from_bytes(content: bytes, suffix: str) -> str:
    if suffix in {".txt", ".md"}:
        try:
            return content.decode("utf-8").strip()
        except UnicodeDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Text and Markdown files must be UTF-8 encoded",
            ) from exc

    if suffix == ".pdf":
        return _extract_pdf_text(content)

    if suffix == ".docx":
        return _extract_docx_text(content)

    raise HTTPException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail="Unsupported document format",
    )


def _extract_pdf_text(content: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(content))

        if reader.is_encrypted:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Encrypted PDF files are not supported",
            )

        pages: list[str] = []

        for page in reader.pages:
            page_text = page.extract_text() or ""
            page_text = page_text.strip()

            if page_text:
                pages.append(page_text)

        text = "\n\n".join(pages).strip()

        if not text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No extractable text found in PDF",
            )

        return text
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to parse PDF: {exc}",
        ) from exc


def _extract_docx_text(content: bytes) -> str:
    try:
        with ZipFile(BytesIO(content)) as archive:
            document_xml = archive.read("word/document.xml")

        root = ElementTree.fromstring(document_xml)
        namespace = {
            "w": (
                "http://schemas.openxmlformats.org/"
                "wordprocessingml/2006/main"
            )
        }

        paragraphs: list[str] = []

        for paragraph in root.findall(".//w:p", namespace):
            text_parts = [
                node.text
                for node in paragraph.findall(".//w:t", namespace)
                if node.text
            ]
            paragraph_text = "".join(text_parts).strip()

            if paragraph_text:
                paragraphs.append(paragraph_text)

        text = "\n".join(paragraphs).strip()

        if not text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No extractable text found in DOCX",
            )

        return text
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to parse DOCX: {exc}",
        ) from exc