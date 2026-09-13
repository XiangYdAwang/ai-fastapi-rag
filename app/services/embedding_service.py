from datetime import datetime, timezone
from typing import Any

import litellm
from fastapi import HTTPException, status

from app.core.config import settings
from app.core.observability import get_observability_client


def _get_value(item: Any, key: str) -> Any:
    if isinstance(item, dict):
        return item[key]

    return getattr(item, key)


async def embed_texts(
    texts: list[str],
    metadata: dict[str, Any] | None = None,
) -> list[list[float]]:
    if not texts:
        return []

    if not settings.embedding_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="EMBEDDING_API_KEY is not configured",
        )

    request_options: dict[str, Any] = {
        "model": settings.embedding_model,
        "input": texts,
        "api_key": settings.embedding_api_key,
    }

    if settings.embedding_api_base:
        request_options["api_base"] = settings.embedding_api_base

    trace_metadata = metadata or {}
    trace_name = str(
        trace_metadata.get("trace_name", "embedding-request")
    )
    tags = [
        str(tag)
        for tag in trace_metadata.get("tags", [])
    ]

    observer = get_observability_client()
    trace = None
    generation = None
    start_time = datetime.now(timezone.utc)

    if observer is not None:
        trace = observer.trace(
            name=trace_name,
            input={"texts": texts},
            metadata=trace_metadata,
            tags=tags,
        )
        generation = trace.generation(
            name="litellm-embedding",
            model=settings.embedding_model,
            input=texts,
            metadata=trace_metadata,
            start_time=start_time,
        )

    try:
        response = await litellm.aembedding(**request_options)

        response_items = sorted(
            response.data,
            key=lambda item: _get_value(item, "index"),
        )

        embeddings = [
            [float(value) for value in _get_value(item, "embedding")]
            for item in response_items
        ]

        if len(embeddings) != len(texts):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Embedding provider returned an unexpected number of vectors",
            )

        for embedding in embeddings:
            if len(embedding) != settings.embedding_dimension:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=(
                        "Embedding dimension mismatch: "
                        f"expected {settings.embedding_dimension}, "
                        f"got {len(embedding)}"
                    ),
                )
    except HTTPException as exc:
        if generation is not None:
            generation.end(
                level="ERROR",
                status_message=str(exc.detail),
                end_time=datetime.now(timezone.utc),
            )
        if trace is not None:
            trace.update(output={"error": exc.detail})
        raise
    except Exception as exc:
        if generation is not None:
            generation.end(
                level="ERROR",
                status_message=str(exc),
                end_time=datetime.now(timezone.utc),
            )
        if trace is not None:
            trace.update(output={"error": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Embedding request failed: {exc}",
        ) from exc

    if generation is not None:
        generation.end(
            output={
                "embedding_count": len(embeddings),
                "embedding_dimensions": len(embeddings[0]) if embeddings else 0,
            },
            end_time=datetime.now(timezone.utc),
        )

    if trace is not None:
        trace.update(
            output={
                "status": "ok",
                "embedding_count": len(embeddings),
            }
        )

    return embeddings