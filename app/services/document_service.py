from pathlib import Path
from uuid import UUID, uuid4

import aiofiles
from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.schemas.document import (
    DocumentUploadResponse,
    EmbedDocumentResponse,
)
from app.services.chunking_service import (
    chunk_document,
    split_text as split_text_with_overlap,
)
from app.services.embedding_service import embed_texts
from app.services.document_parser import extract_text_from_bytes

ALLOWED_SUFFIXES = {".txt", ".md", ".pdf", ".docx"}


def split_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    return split_text_with_overlap(
        text=text,
        chunk_size=chunk_size,
        overlap=overlap,
    )


async def create_document_from_upload(
    file: UploadFile,
    db: AsyncSession,
) -> DocumentUploadResponse:
    original_filename = Path(file.filename or "").name

    if not original_filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required",
        )

    suffix = Path(original_filename).suffix.lower()

    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Supported formats: .txt, .md, .pdf, .docx",
        )

    content = await file.read()
    file_size = len(content)

    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty",
        )

    max_file_size = settings.max_upload_size_mb * 1024 * 1024

    if file_size > max_file_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {settings.max_upload_size_mb} MB",
        )

    text = extract_text_from_bytes(
        content=content,
        suffix=suffix,
    )

    chunks = chunk_document(
        text=text,
        suffix=suffix,
        source_path=original_filename,
    )

    document_id = uuid4()
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    stored_path = upload_dir / str(document_id)

    async with aiofiles.open(stored_path, "wb") as target:
        await target.write(content)

    document = Document(
        id=document_id,
        filename=original_filename,
        content_type=file.content_type,
        file_size=file_size,
        status="processing",
    )

    try:
        db.add(document)
        await db.flush()

        for chunk_index, chunk in enumerate(chunks):
            db.add(
                DocumentChunk(
                    document_id=document_id,
                    chunk_index=chunk_index,
                    content=chunk.content,
                    embedding=None,
                    extra_metadata={
                        "source_filename": original_filename,
                        **chunk.metadata,
                    },
                )
            )

        document.status = "processed" if chunks else "empty"

        await db.commit()
        await db.refresh(document)
    except Exception:
        await db.rollback()
        stored_path.unlink(missing_ok=True)
        raise

    return DocumentUploadResponse(
        id=document.id,
        filename=document.filename,
        content_type=document.content_type,
        file_size=document.file_size,
        status=document.status,
        chunks_created=len(chunks),
        created_at=document.created_at,
    )


async def embed_document(
    document_id: UUID,
    db: AsyncSession,
) -> EmbedDocumentResponse:
    document = await db.get(Document, document_id)

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    result = await db.execute(
        select(DocumentChunk)
        .where(
            DocumentChunk.document_id == document_id,
            DocumentChunk.embedding.is_(None),
        )
        .order_by(DocumentChunk.chunk_index)
    )
    chunks = list(result.scalars().all())

    if not chunks:
        return EmbedDocumentResponse(
            document_id=document.id,
            embedded_chunks=0,
            status=document.status,
        )

    try:
        for start in range(0, len(chunks), settings.embedding_batch_size):
            batch = chunks[start : start + settings.embedding_batch_size]
            embeddings = await embed_texts(
                [chunk.content for chunk in batch],
                metadata={
                    "trace_name": f"embed-document-{document_id}",
                    "tags": ["embedding", "document"],
                    "document_id": str(document_id),
                },
            )

            for chunk, embedding in zip(batch, embeddings, strict=True):
                chunk.embedding = embedding

        document.status = "completed"
        await db.commit()
        await db.refresh(document)
    except Exception:
        await db.rollback()
        raise

    return EmbedDocumentResponse(
        document_id=document.id,
        embedded_chunks=len(chunks),
        status=document.status,
    )