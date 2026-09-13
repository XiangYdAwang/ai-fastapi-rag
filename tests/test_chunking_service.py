from app.core.config import settings
from app.services.chunking_service import chunk_document


def test_markdown_chunking_preserves_non_python_code_fence() -> None:
    text = (
        "# Source: config/app.yaml\n\n"
        "<!-- source_path: config/app.yaml -->\n\n"
        "```yaml\n"
        "# This is a YAML comment, not a Markdown heading.\n"
        "port: 8000\n"
        "```\n\n"
        "## Notes\n\n"
        "Additional explanation.\n"
    )

    chunks = chunk_document(
        text=text,
        suffix=".md",
        source_path="snapshot.md",
    )

    assert len(chunks) == 3
    assert chunks[0].metadata["source_path"] == "config/app.yaml"
    assert any(
        "# This is a YAML comment" in chunk.content
        for chunk in chunks
    )
    assert chunks[-1].metadata["heading"] == "Notes"


def test_python_code_block_defaults_to_structural_block(
    monkeypatch,
) -> None:
    text = (
        "# Source: app/demo.py\n\n"
        "<!-- source_path: app/demo.py -->\n\n"
        "```python\n"
        "def demo(value: str) -> str:\n"
        "    return value.upper()\n"
        "```\n"
    )

    monkeypatch.setattr(settings, "ast_chunking_enabled", False)
    chunks = chunk_document(
        text=text,
        suffix=".md",
        source_path="snapshot.md",
    )

    assert any(
        chunk.metadata.get("chunk_type") == "code_block" and
        "def demo" in chunk.content
        for chunk in chunks
    )
    assert not any(
        chunk.metadata.get("chunk_type") == "python_code"
        for chunk in chunks
    )


def test_python_code_block_can_be_split_by_symbol(
    monkeypatch,
) -> None:
    text = (
        "# Source: app/demo.py\n\n"
        "<!-- source_path: app/demo.py -->\n\n"
        "```python\n"
        "import os\n\n"
        "@decorator\n"
        "def demo(value: str) -> str:\n"
        "    return value.upper()\n\n"
        "class Service:\n"
        "    def run(self) -> None:\n"
        "        pass\n"
        "```\n"
    )

    monkeypatch.setattr(settings, "ast_chunking_enabled", True)
    chunks = chunk_document(
        text=text,
        suffix=".md",
        source_path="snapshot.md",
    )

    symbol_chunks = {
        chunk.metadata.get("symbol_name"): chunk
        for chunk in chunks
        if chunk.metadata.get("chunk_type") == "python_code"
    }

    assert "module" in symbol_chunks
    assert "demo" in symbol_chunks
    assert "Service" in symbol_chunks
    assert symbol_chunks["demo"].metadata["symbol_type"] == "function"
    assert symbol_chunks["Service"].metadata["symbol_type"] == "class"
    assert "@decorator" in symbol_chunks["demo"].content
    assert symbol_chunks["demo"].metadata["start_line"] == 3
    assert symbol_chunks["demo"].metadata["end_line"] == 5


def test_generic_chunking_adds_metadata() -> None:
    chunks = chunk_document(
        text="abcdefghij",
        suffix=".txt",
        source_path="sample.txt",
    )

    assert len(chunks) == 1
    assert chunks[0].content == "abcdefghij"
    assert chunks[0].metadata["source_path"] == "sample.txt"
    assert chunks[0].metadata["chunk_type"] == "text"

def test_parent_child_chunking_keeps_parent_context(
    monkeypatch,
) -> None:
    text = "A" * 120

    monkeypatch.setattr(settings, "parent_child_enabled", True)
    monkeypatch.setattr(settings, "child_chunk_size", 50)
    monkeypatch.setattr(settings, "child_chunk_overlap", 10)

    chunks = chunk_document(
        text=text,
        suffix=".txt",
        source_path="sample.txt",
    )

    assert len(chunks) > 1
    assert all(
        chunk.metadata["chunk_role"] == "child"
        for chunk in chunks
    )
    assert all(
        chunk.metadata["parent_content"] == text
        for chunk in chunks
    )
