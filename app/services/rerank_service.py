import logging
from datetime import datetime, timezone

import httpx

from app.core.config import settings
from app.core.observability import get_observability_client
from app.schemas.search import SearchResult

logger = logging.getLogger(__name__)


async def rerank_results(
    query: str,
    results: list[SearchResult],
    top_k: int,
) -> list[SearchResult]:
    if not results:
        return []

    if not settings.rerank_enabled:
        return results[:top_k]

    api_key = settings.rerank_api_key or settings.embedding_api_key
    api_base = settings.rerank_api_base or settings.embedding_api_base

    if not api_key or not api_base:
        logger.warning(
            "Rerank skipped: API key or API base is not configured"
        )
        return results[:top_k]

    endpoint = f"{api_base.rstrip('/')}/rerank"
    payload = {
        "model": settings.rerank_model,
        "query": query,
        "documents": [result.content for result in results],
        "top_n": min(top_k, len(results)),
        "return_documents": False,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
    }

    observer = get_observability_client()
    trace = None
    generation = None
    start_time = datetime.now(timezone.utc)

    if observer is not None:
        trace = observer.trace(
            name="rerank-results",
            input={
                "query": query,
                "candidate_count": len(results),
            },
            metadata={
                "model": settings.rerank_model,
            },
            tags=["rerank", "search"],
        )
        generation = trace.generation(
            name="siliconflow-rerank",
            model=settings.rerank_model,
            input={
                "query": query,
                "candidate_count": len(results),
            },
            start_time=start_time,
        )

    try:
        async with httpx.AsyncClient(
            timeout=settings.rerank_timeout_seconds
        ) as client:
            response = await client.post(
                endpoint,
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        returned_items = data.get("results", [])

        if not returned_items:
            raise ValueError("Rerank provider returned no results")

        reranked: list[SearchResult] = []

        for item in returned_items:
            index = int(item["index"])

            if index < 0 or index >= len(results):
                continue

            relevance_score = float(item["relevance_score"])
            reranked.append(
                results[index].model_copy(
                    update={
                        "score": relevance_score,
                        "rerank_score": relevance_score,
                    }
                )
            )
    except Exception as exc:
        logger.exception("Rerank request failed")

        if generation is not None:
            generation.end(
                level="ERROR",
                status_message=str(exc),
                end_time=datetime.now(timezone.utc),
            )

        if trace is not None:
            trace.update(output={"error": str(exc)})

        return results[:top_k]

    token_usage = data.get("meta", {}).get("tokens", {})
    input_tokens = int(token_usage.get("input_tokens", 0) or 0)

    if generation is not None:
        generation.end(
            output={
                "top_n": len(reranked),
            },
            usage_details={
                "input": input_tokens,
                "total": input_tokens,
            },
            end_time=datetime.now(timezone.utc),
        )

    if trace is not None:
        trace.update(
            output={
                "status": "ok",
                "top_n": len(reranked),
            }
        )

    return reranked[:top_k]