from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)
    document_id: UUID | None = None
    min_score: float | None = Field(default=None, ge=-1.0, le=1.0)


class SearchResult(BaseModel):
    chunk_id: UUID
    document_id: UUID
    filename: str
    chunk_index: int
    content: str
    score: float
    vector_score: float | None = None
    lexical_score: float | None = None
    retrieval_score: float | None = None
    rerank_score: float | None = None
    matched_content: str | None = None
    retrieval_metadata: dict[str, Any] | None = None


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]