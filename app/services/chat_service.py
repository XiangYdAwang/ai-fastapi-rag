import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, AsyncIterator

import litellm
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.observability import get_observability_client
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.search import SearchRequest, SearchResult
from app.services.search_service import search_documents

SYSTEM_PROMPT = """
你是一个基于知识库回答问题的助手。

规则：
1. 只能依据用户提供的资料回答，不要编造资料中不存在的信息。
2. 如果资料不足，明确回答“根据现有资料无法回答”。
3. 引用资料时使用 [1]、[2] 这样的编号。
4. 回答应简洁、准确，并使用与问题相同的语言。
""".strip()


@dataclass
class PreparedChat:
    context: str
    sources: list[SearchResult]
    messages: list[dict[str, str]]
    request_options: dict[str, Any]


def _sse_event(event: str, payload: dict[str, Any]) -> str:
    data = json.dumps(payload, ensure_ascii=False)
    return f"event: {event}\ndata: {data}\n\n"


def _get_usage_details(response: Any) -> dict[str, int] | None:
    usage = getattr(response, "usage", None)

    if usage is None:
        return None

    input_tokens = getattr(usage, "prompt_tokens", 0) or 0
    output_tokens = getattr(usage, "completion_tokens", 0) or 0

    return {
        "input": int(input_tokens),
        "output": int(output_tokens),
        "total": int(input_tokens) + int(output_tokens),
    }


def _build_context(
    results: list[SearchResult],
) -> tuple[str, list[SearchResult]]:
    blocks: list[str] = []
    included_sources: list[SearchResult] = []
    used_chars = 0

    for index, result in enumerate(results, start=1):
        block = (
            f"[{index}] 来源文件：{result.filename}\n"
            f"文本块序号：{result.chunk_index}\n"
            f"内容：{result.content}"
        )

        if (
            blocks
            and used_chars + len(block) > settings.chat_max_context_chars
        ):
            break

        blocks.append(block)
        included_sources.append(result)
        used_chars += len(block)

    return "\n\n".join(blocks), included_sources


async def _prepare_chat(
    request: ChatRequest,
    db: AsyncSession,
) -> PreparedChat | None:
    search_response = await search_documents(
        request=SearchRequest(
            query=request.query,
            top_k=request.top_k,
            document_id=request.document_id,
            min_score=request.min_score,
        ),
        db=db,
    )

    if not search_response.results:
        return None

    context, sources = _build_context(search_response.results)
    api_key = settings.chat_api_key or settings.embedding_api_key
    api_base = settings.chat_api_base or settings.embedding_api_base

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="CHAT_API_KEY or EMBEDDING_API_KEY is not configured",
        )

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": (
                f"资料：\n\n{context}\n\n"
                f"问题：\n{request.query}"
            ),
        },
    ]

    request_options: dict[str, Any] = {
        "model": settings.chat_model,
        "messages": messages,
        "api_key": api_key,
        "temperature": request.temperature,
        "max_tokens": settings.chat_max_tokens,
    }

    if api_base:
        request_options["api_base"] = api_base

    return PreparedChat(
        context=context,
        sources=sources,
        messages=messages,
        request_options=request_options,
    )


def _start_generation(
    request: ChatRequest,
    prepared: PreparedChat,
) -> tuple[Any, Any, Any]:
    observer = get_observability_client()
    trace = None
    generation = None
    start_time = datetime.now(timezone.utc)

    if observer is not None:
        trace = observer.trace(
            name="rag-chat",
            input={
                "query": request.query,
                "context": prepared.context,
            },
            metadata={
                "top_k": request.top_k,
                "document_id": (
                    str(request.document_id)
                    if request.document_id
                    else None
                ),
            },
            tags=["rag", "chat"],
        )
        generation = trace.generation(
            name="litellm-chat",
            model=settings.chat_model,
            input=prepared.messages,
            start_time=start_time,
        )

    return trace, generation, start_time


def _finish_generation_error(
    trace: Any,
    generation: Any,
    error: str,
) -> None:
    if generation is not None:
        generation.end(
            level="ERROR",
            status_message=error,
            end_time=datetime.now(timezone.utc),
        )

    if trace is not None:
        trace.update(output={"error": error})


async def answer_question(
    request: ChatRequest,
    db: AsyncSession,
) -> ChatResponse:
    prepared = await _prepare_chat(request=request, db=db)

    if prepared is None:
        return ChatResponse(
            answer="根据现有资料无法回答。",
            sources=[],
        )

    trace, generation, _ = _start_generation(
        request=request,
        prepared=prepared,
    )

    try:
        response = await litellm.acompletion(**prepared.request_options)
        answer = response.choices[0].message.content or ""

        if not answer.strip():
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Chat model returned an empty response",
            )
    except HTTPException as exc:
        _finish_generation_error(
            trace=trace,
            generation=generation,
            error=str(exc.detail),
        )
        raise
    except Exception as exc:
        _finish_generation_error(
            trace=trace,
            generation=generation,
            error=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Chat request failed: {exc}",
        ) from exc

    if generation is not None:
        generation.end(
            output=answer,
            usage_details=_get_usage_details(response),
            end_time=datetime.now(timezone.utc),
        )

    if trace is not None:
        trace.update(
            output={
                "answer": answer,
                "source_count": len(prepared.sources),
            }
        )

    return ChatResponse(
        answer=answer,
        sources=prepared.sources,
    )


async def stream_answer(
    request: ChatRequest,
    db: AsyncSession,
) -> AsyncIterator[str]:
    fallback_answer = "根据现有资料无法回答。"
    prepared = await _prepare_chat(request=request, db=db)

    if prepared is None:
        yield _sse_event("sources", {"sources": []})
        yield _sse_event("token", {"content": fallback_answer})
        yield _sse_event("done", {"answer": fallback_answer})
        return

    serialized_sources = [
        source.model_dump(mode="json")
        for source in prepared.sources
    ]
    yield _sse_event("sources", {"sources": serialized_sources})

    trace, generation, _ = _start_generation(
        request=request,
        prepared=prepared,
    )
    full_answer = ""

    try:
        stream = await litellm.acompletion(
            **prepared.request_options,
            stream=True,
        )

        async for chunk in stream:
            choices = getattr(chunk, "choices", None)

            if not choices:
                continue

            delta = getattr(choices[0], "delta", None)
            content = getattr(delta, "content", None) if delta else None

            if content:
                full_answer += content
                yield _sse_event("token", {"content": content})

        if not full_answer.strip():
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Chat model returned an empty response",
            )
    except HTTPException as exc:
        _finish_generation_error(
            trace=trace,
            generation=generation,
            error=str(exc.detail),
        )
        yield _sse_event("error", {"detail": exc.detail})
        return
    except Exception as exc:
        _finish_generation_error(
            trace=trace,
            generation=generation,
            error=str(exc),
        )
        yield _sse_event(
            "error",
            {"detail": f"Chat request failed: {exc}"},
        )
        return

    if generation is not None:
        generation.end(
            output=full_answer,
            end_time=datetime.now(timezone.utc),
        )

    if trace is not None:
        trace.update(
            output={
                "answer": full_answer,
                "source_count": len(prepared.sources),
                "stream": True,
            }
        )

    yield _sse_event("done", {"answer": full_answer})