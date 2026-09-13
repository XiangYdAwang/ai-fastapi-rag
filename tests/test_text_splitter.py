import pytest

from app.services.document_service import split_text


def test_split_text_with_overlap() -> None:
    assert split_text("abcdefghij", chunk_size=4, overlap=1) == [
        "abcd",
        "defg",
        "ghij",
    ]


def test_split_text_returns_empty_for_whitespace() -> None:
    assert split_text(" \n\t ", chunk_size=10, overlap=2) == []


def test_split_text_rejects_invalid_overlap() -> None:
    with pytest.raises(ValueError):
        split_text("abcdef", chunk_size=4, overlap=4)