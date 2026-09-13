import json
from pathlib import Path

SOURCE_FILES = [
    "README.md",
    "docs/architecture.md",
    "docs/evaluation.md",
    "app/main.py",
    "app/core/config.py",
    "app/core/observability.py",
    "app/db/session.py",
    "app/models/document.py",
    "app/models/document_chunk.py",
    "app/schemas/search.py",
    "app/schemas/chat.py",
    "app/services/document_parser.py",
    "app/services/document_service.py",
    "app/services/embedding_service.py",
    "app/services/search_service.py",
    "app/services/rerank_service.py",
    "app/services/chat_service.py",
    "app/api/documents.py",
    "app/api/search.py",
    "app/api/chat.py",
    "migrations/versions/a8723260ab00_create_documents_and_document_chunks.py",
    "migrations/versions/b1f2c3d4e5f6_enable_pg_trgm_and_content_index.py",
    "docker/initdb/001-enable-pgvector.sql",
    "docker/initdb/002-enable-pgtrgm.sql",
    "scripts/evaluate_retrieval.py",
    "scripts/import_evaluation_corpus.py",
    "tests/test_rerank_service.py",
    "requirements.txt",
    "docker-compose.yml",
]


def snapshot_name(source_path: str) -> str:
    return (
        source_path.replace("/", "__")
        .replace("\\", "__")
        .replace(".", "_")
        + ".md"
    )


def code_fence_language(source_path: str) -> str:
    suffix = Path(source_path).suffix.lower()

    return {
        ".py": "python",
        ".md": "markdown",
        ".yml": "yaml",
        ".yaml": "yaml",
        ".toml": "toml",
        ".sql": "sql",
        ".txt": "text",
    }.get(suffix, "text")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    output_dir = root / "evaluation" / "project_corpus"
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest: list[dict[str, str]] = []

    for source_path in SOURCE_FILES:
        source = root / source_path

        if not source.exists():
            raise FileNotFoundError(source)

        content = source.read_text(encoding="utf-8")
        name = snapshot_name(source_path)
        target = output_dir / name

        if source.suffix.lower() == ".md":
            snapshot = (
                f"# Source: {source_path}\n\n"
                f"<!-- source_path: {source_path} -->\n\n"
                f"{content}\n"
            )
        else:
            language = code_fence_language(source_path)
            snapshot = (
                f"# Source: {source_path}\n\n"
                f"<!-- source_path: {source_path} -->\n\n"
                f"```{language}\n"
                f"{content}\n"
                f"```\n"
            )

        target.write_text(snapshot, encoding="utf-8")
        manifest.append(
            {
                "source_path": source_path,
                "snapshot": name,
            }
        )

    questions = [
        ("Which endpoint uploads a document?", "app/api/documents.py", ["/upload"]),
        ("Which endpoint generates embeddings for a document?", "app/api/documents.py", ["/{document_id}/embed"]),
        ("Which route performs retrieval search?", "app/api/search.py", ["/search"]),
        ("Which route performs RAG chat?", "app/api/chat.py", ["/chat"]),
        ("What is the default text chunk size?", "app/core/config.py", ["chunk_size: int = 1000"]),
        ("What is the default chunk overlap?", "app/core/config.py", ["chunk_overlap: int = 200"]),
        ("What embedding dimension is configured?", "app/core/config.py", ["embedding_dimension: int = 1024"]),
        ("Which embedding model is configured?", "app/core/config.py", ["BAAI/bge-m3"]),
        ("Which rerank model is configured?", "app/core/config.py", ["BAAI/bge-reranker-v2-m3"]),
        ("What is the rerank timeout?", "app/core/config.py", ["rerank_timeout_seconds: float = 30.0"]),
        ("What constant is used for reciprocal rank fusion?", "app/services/search_service.py", ["RRF_K = 60"]),
        ("How is the hybrid candidate limit calculated?", "app/services/search_service.py", ["candidate_limit = max(request.top_k * 4, 20)"]),
        ("Which fields expose vector, lexical, retrieval, and rerank scores?", "app/schemas/search.py", ["vector_score", "lexical_score", "retrieval_score", "rerank_score"]),
        ("What happens when the rerank request fails?", "app/services/rerank_service.py", ["Rerank request failed", "return results[:top_k]"]),
        ("Which standard-library modules parse DOCX files?", "app/services/document_parser.py", ["ZipFile", "ElementTree"]),
        ("Which library parses PDF files?", "app/services/document_parser.py", ["PdfReader"]),
        ("Which document formats are allowed?", "app/services/document_service.py", ["ALLOWED_SUFFIXES", ".pdf", ".docx"]),
        ("Which setting controls the maximum upload size?", "app/services/document_service.py", ["max_upload_size"]),
        ("Which session factory is used by the API?", "app/db/session.py", ["AsyncSessionLocal"]),
        ("Which database table stores documents?", "app/models/document.py", ["__tablename__ = \"documents\""]),
        ("Which database type stores chunk metadata?", "app/models/document_chunk.py", ["JSONB", "metadata"]),
        ("Which extension enables vector columns?", "docker/initdb/001-enable-pgvector.sql", ["CREATE EXTENSION IF NOT EXISTS vector"]),
        ("Which extension enables trigram search?", "docker/initdb/002-enable-pgtrgm.sql", ["CREATE EXTENSION IF NOT EXISTS pg_trgm"]),
        ("Which metric records first-result hit rate?", "scripts/evaluate_retrieval.py", ["hit_rate_at_1"]),
        ("How is MRR accumulated?", "scripts/evaluate_retrieval.py", ["reciprocal_rank_sum"]),
        ("Which test verifies rerank fallback on errors?", "tests/test_rerank_service.py", ["test_rerank_falls_back_on_error"]),
        ("Which log message confirms that Langfuse tracing is enabled?", "app/core/observability.py", ["Langfuse tracing enabled"]),
        ("Which setting provides the Langfuse host to the SDK?", "app/core/observability.py", ["settings.langfuse_host"]),
        ("Which setting limits RAG context size?", "app/services/chat_service.py", ["chat_max_context_chars"]),
        ("Which default chat model is configured?", "app/core/config.py", ["openai/Qwen/Qwen2.5-7B-Instruct"]),
    ]

    qa_lines: list[dict[str, object]] = []

    for index, (question, source_path, keywords) in enumerate(questions, start=1):
        if source_path not in SOURCE_FILES:
            raise ValueError(f"Question source is missing: {source_path}")

        qa_lines.append(
            {
                "id": f"project-{index:02d}",
                "question": question,
                "expected_document": snapshot_name(source_path),
                "expected_keywords": keywords,
            }
        )

    manifest_path = root / "evaluation" / "project_corpus_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    qa_path = root / "evaluation" / "qa_dataset_project.jsonl"
    qa_path.write_text(
        "\n".join(
            json.dumps(line, ensure_ascii=False)
            for line in qa_lines
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"documents={len(manifest)}")
    print(f"questions={len(qa_lines)}")
    print(f"corpus_dir={output_dir}")
    print(f"manifest={manifest_path}")
    print(f"qa_dataset={qa_path}")


if __name__ == "__main__":
    main()