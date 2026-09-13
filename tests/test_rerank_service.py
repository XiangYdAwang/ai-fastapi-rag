import asyncio
from uuid import uuid4

import httpx
import pytest

from app.core.config import settings
from app.schemas.search import SearchResult
import app.services.rerank_service as rerank_service
from app.services.rerank_service import rerank_results


def make_result(index: int, filename: str) -> SearchResult:
    return SearchResult(
        chunk_id=uuid4(),
        document_id=uuid4(),
        filename=filename,
        chunk_index=index,
        content=f"content-{index}",
        score=0.5,
        retrieval_score=0.5,
    )


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


def make_fake_client(response=None, error=None):
    class FakeAsyncClient:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, *args, **kwargs):
            if error is not None:
                raise error
            return response

    return FakeAsyncClient


def test_rerank_returns_candidates_in_provider_order(monkeypatch) -> None:
    first = make_result(0, "first.md")
    second = make_result(1, "second.md")
    payload = {
        "results": [
            {"index": 1, "relevance_score": 0.95},
            {"index": 0, "relevance_score": 0.10},
        ],
        "meta": {"tokens": {"input_tokens": 12}},
    }

    monkeypatch.setattr(settings, "rerank_enabled", True)
    monkeypatch.setattr(settings, "rerank_api_key", "test-key")
    monkeypatch.setattr(
        settings,
        "rerank_api_base",
        "https://example.com/v1",
    )
    monkeypatch.setattr(
        rerank_service.httpx,
        "AsyncClient",
        make_fake_client(response=FakeResponse(payload)),
    )

    results = asyncio.run(
        rerank_results("query", [first, second], top_k=2)
    )

    assert [item.chunk_id for item in results] == [
        second.chunk_id,
        first.chunk_id,
    ]
    assert results[0].rerank_score == 0.95


def test_rerank_falls_back_on_error(monkeypatch) -> None:
    first = make_result(0, "first.md")
    second = make_result(1, "second.md")

    monkeypatch.setattr(settings, "rerank_enabled", True)
    monkeypatch.setattr(settings, "rerank_api_key", "test-key")
    monkeypatch.setattr(
        settings,
        "rerank_api_base",
        "https://example.com/v1",
    )
    monkeypatch.setattr(
        rerank_service.httpx,
        "AsyncClient",
        make_fake_client(error=httpx.ConnectError("failed")),
    )

    results = asyncio.run(
        rerank_results("query", [first, second], top_k=2)
    )

    assert [item.chunk_id for item in results] == [
        first.chunk_id,
        second.chunk_id,
    ]


def test_rerank_can_be_disabled(monkeypatch) -> None:
    first = make_result(0, "first.md")
    second = make_result(1, "second.md")

    monkeypatch.setattr(settings, "rerank_enabled", False)

    results = asyncio.run(
        rerank_results("query", [first, second], top_k=1)
    )

    assert results == [first]