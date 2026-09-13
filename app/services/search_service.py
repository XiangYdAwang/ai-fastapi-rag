from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.schemas.search import (
    SearchRequest,
    SearchResponse,
    SearchResult,
)
from app.services.embedding_service import embed_texts
from app.services.rerank_service import rerank_results
RRF_K = 60


def _new_ranked_item(row: Any) -> dict[str, Any]:
    return {
        "chunk_id": row["chunk_id"],
        "document_id": row["document_id"],
        "filename": row["filename"],
        "chunk_index": row["chunk_index"],
        "content": row["content"],
        "vector_score": None,
        "lexical_score": None,
        "rrf_score": 0.0,
        "retrieval_metadata": row["retrieval_metadata"],
    }


def _add_rank(
    item: dict[str, Any],
    rank: int,
) -> None:
    item["rrf_score"] += 1.0 / (RRF_K + rank)


async def search_documents(
    request: SearchRequest,
    db: AsyncSession,
) -> SearchResponse:
    query = request.query.strip()

    if not query:
        return SearchResponse(query=request.query, results=[])

    query_embedding = (
        await embed_texts(
            [query],
            metadata={
                "trace_name": "search-query-embedding",
                "tags": ["embedding", "search"],
                "retrieval_mode": "hybrid",
            },
        )
    )[0]

    candidate_limit = max(request.top_k * 4, 20)

    vector_distance = DocumentChunk.embedding.cosine_distance(
        query_embedding
    )
    vector_score = (1 - vector_distance).label("vector_score")

    vector_statement = (
        select(
            DocumentChunk.id.label("chunk_id"),
            DocumentChunk.document_id.label("document_id"),
            DocumentChunk.chunk_index.label("chunk_index"),
            DocumentChunk.content.label("content"),
            Document.filename.label("filename"),
            DocumentChunk.extra_metadata.label("retrieval_metadata"),
            vector_score,
        )
        .join(
            Document,
            Document.id == DocumentChunk.document_id,
        )
        .where(DocumentChunk.embedding.is_not(None))
    )

    lexical_score = func.similarity(
        func.lower(DocumentChunk.content),
        query.casefold(),
    ).label("lexical_score")

    lexical_statement = (
        select(
            DocumentChunk.id.label("chunk_id"),
            DocumentChunk.document_id.label("document_id"),
            DocumentChunk.chunk_index.label("chunk_index"),
            DocumentChunk.content.label("content"),
            Document.filename.label("filename"),
            DocumentChunk.extra_metadata.label("retrieval_metadata"),
            lexical_score,
        )
        .join(
            Document,
            Document.id == DocumentChunk.document_id,
        )
        .where(lexical_score > 0.0)
    )

    if request.document_id is not None:
        vector_statement = vector_statement.where(
            DocumentChunk.document_id == request.document_id
        )
        lexical_statement = lexical_statement.where(
            DocumentChunk.document_id == request.document_id
        )

    vector_rows = (
        await db.execute(
            vector_statement
            .order_by(vector_distance)
            .limit(candidate_limit)
        )
    ).mappings().all()

    lexical_rows = (
        await db.execute(
            lexical_statement
            .order_by(lexical_score.desc())
            .limit(candidate_limit)
        )
    ).mappings().all()

    ranked: dict[UUID, dict[str, Any]] = {}

    for rank, row in enumerate(vector_rows, start=1):
        item = ranked.setdefault(
            row["chunk_id"],
            _new_ranked_item(row),
        )
        item["vector_score"] = float(row["vector_score"])
        _add_rank(item, rank)

    for rank, row in enumerate(lexical_rows, start=1):
        item = ranked.setdefault(
            row["chunk_id"],
            _new_ranked_item(row),
        )
        item["lexical_score"] = float(row["lexical_score"])
        _add_rank(item, rank)

    items = list(ranked.values())

    if request.min_score is not None:
        items = [
            item
            for item in items
            if (
                item["vector_score"] is not None
                and item["vector_score"] >= request.min_score
            )
        ]

    items.sort(
        key=lambda item: (
            item["rrf_score"],
            item["vector_score"]
            if item["vector_score"] is not None
            else -1.0,
            item["lexical_score"]
            if item["lexical_score"] is not None
            else -1.0,
        ),
        reverse=True,
    )

    retrieval_score = round(item["rrf_score"], 6)

    results = [
        SearchResult(
            chunk_id=item["chunk_id"],
            document_id=item["document_id"],
            filename=item["filename"],
            chunk_index=item["chunk_index"],
            content=item["content"],
            score=round(item["rrf_score"], 6),
            retrieval_score=round(item["rrf_score"], 6),
            matched_content=item["content"],
            retrieval_metadata=item["retrieval_metadata"],
            vector_score=(
                round(item["vector_score"], 6)
                if item["vector_score"] is not None
                else None
            ),
            lexical_score=(
                round(item["lexical_score"], 6)
                if item["lexical_score"] is not None
                else None
            ),
        )
        for item in items
    ]

    reranked_results = await rerank_results(
        query=query,
        results=results,
        top_k=request.top_k,
    )

    expanded_results = []

    for result in reranked_results:
        metadata = result.retrieval_metadata or {}
        parent_content = metadata.get("parent_content")

        if isinstance(parent_content, str) and parent_content:
            expanded_results.append(
                result.model_copy(
                    update={
                        "content": parent_content,
                    }
                )
            )
        else:
            expanded_results.append(result)

    return SearchResponse(
        query=query,
        results=expanded_results,
    )