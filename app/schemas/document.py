from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class DocumentUploadResponse(BaseModel):
    id: UUID
    filename: str
    content_type: str | None
    file_size: int
    status: str
    chunks_created: int
    created_at: datetime


class EmbedDocumentResponse(BaseModel):
    document_id: UUID
    embedded_chunks: int
    status: str
    # 定义上传接口的返回格式