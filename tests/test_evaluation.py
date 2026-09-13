from pathlib import Path
from uuid import uuid4

from app.schemas.search import SearchResult
from scripts.evaluate_retrieval import is_relevant, load_dataset


def make_result(filename: str, content: str) -> SearchResult:
    return SearchResult(
        chunk_id=uuid4(),
        document_id=uuid4(),
        filename=filename,
        chunk_index=0,
        content=content,
        score=1.0,
    )


def test_load_dataset_reads_jsonl(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text(
        '{"id":"q1","question":"test",'
        '"expected_document":"doc.md",'
        '"expected_keywords":["answer"]}\n',
        encoding="utf-8",
    )

    cases = load_dataset(dataset)

    assert len(cases) == 1
    assert cases[0]["id"] == "q1"


def test_is_relevant_checks_document_and_keywords() -> None:
    case = {
        "expected_document": "doc.md",
        "expected_keywords": ["vector"],
    }

    assert is_relevant(make_result("doc.md", "vector search"), case)
    assert not is_relevant(make_result("other.md", "vector search"), case)
    assert not is_relevant(make_result("doc.md", "database"), case)