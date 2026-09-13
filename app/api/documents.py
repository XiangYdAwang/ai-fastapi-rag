from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.document import (
    DocumentUploadResponse,
    EmbedDocumentResponse,
)
from app.services.document_service import (
    create_document_from_upload,
    embed_document,
)

router = APIRouter(
    prefix="/api/documents",
    tags=["documents"],
)


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
        file: Annotated[
            UploadFile,
            File(description="Supported: .txt, .md, .pdf, .docx"),
        ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DocumentUploadResponse:
    return await create_document_from_upload(file=file, db=db)


@router.post(
    "/{document_id}/embed",
    response_model=EmbedDocumentResponse,
)
async def embed_document_endpoint(
    document_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> EmbedDocumentResponse:
    return await embed_document(document_id=document_id, db=db)