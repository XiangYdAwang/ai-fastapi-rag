import os

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://test:test@localhost:5432/test",
)
os.environ.setdefault("LANGFUSE_ENABLED", "false")
os.environ.setdefault("EMBEDDING_API_KEY", "test-key")
os.environ.setdefault(
    "EMBEDDING_API_BASE",
    "https://example.com/v1",
)
os.environ.setdefault("RERANK_ENABLED", "true")