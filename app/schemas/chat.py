from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.search import SearchResult


class ChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)
    document_id: UUID | None = None
    min_score: float | None = Field(default=None, ge=-1.0, le=1.0)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)


class ChatResponse(BaseModel):
    answer: str
    sources: list[SearchResult]