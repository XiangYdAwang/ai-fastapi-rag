import asyncio
from types import SimpleNamespace
from uuid import uuid4

import app.services.chat_service as chat_service
from app.core.config import settings
from app.schemas.chat import ChatRequest
from app.schemas.search import SearchResponse, SearchResult


class FakeStream:
    def __init__(self, contents: list[str]) -> None:
        self._items = iter(contents)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            content = next(self._items)
        except StopIteration as exc:
            raise StopAsyncIteration from exc

        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(content=content),
                )
            ]
        )


def test_sse_event_format() -> None:
    event = chat_service._sse_event(
        "token",
        {"content": "hello"},
    )

    assert event == (
        'event: token\n'
        'data: {"content": "hello"}\n\n'
    )


def test_stream_answer_emits_sources_tokens_and_done(
    monkeypatch,
) -> None:
    source = SearchResult(
        chunk_id=uuid4(),
        document_id=uuid4(),
        filename="sample.md",
        chunk_index=0,
        content="FastAPI is a Python web framework.",
        score=1.0,
    )

    async def fake_search_documents(request, db):
        return SearchResponse(query=request.query, results=[source])

    async def fake_acompletion(**kwargs):
        assert kwargs["stream"] is True
        return FakeStream(["FastAPI", " is", " Python."])

    monkeypatch.setattr(
        chat_service,
        "search_documents",
        fake_search_documents,
    )
    monkeypatch.setattr(
        chat_service.litellm,
        "acompletion",
        fake_acompletion,
    )
    monkeypatch.setattr(
        settings,
        "chat_api_key",
        "test-key",
    )

    async def collect_events() -> list[str]:
        return [
            event
            async for event in chat_service.stream_answer(
                ChatRequest(query="What is FastAPI?"),
                db=None,
            )
        ]

    events = asyncio.run(collect_events())

    assert any(event.startswith("event: sources") for event in events)
    assert events.count(
        'event: token\ndata: {"content": "FastAPI"}\n\n'
    ) == 1
    assert events[-1] == (
        'event: done\n'
        'data: {"answer": "FastAPI is Python."}\n\n'
    )