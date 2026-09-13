from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI FastAPI RAG"
    database_url: str

    upload_dir: Path = Path("data/uploads")
    max_upload_size_mb: int = 20
    chunk_size: int = 1000
    chunk_overlap: int = 200
    structured_chunk_size: int = 4000
    ast_chunking_enabled: bool = False
    parent_child_enabled: bool = False
    child_chunk_size: int = 800
    child_chunk_overlap: int = 100

    embedding_model: str = "openai/BAAI/bge-m3"
    embedding_api_key: str | None = None
    embedding_api_base: str | None = None
    embedding_batch_size: int = 32
    embedding_dimension: int = 1024

    chat_model: str = "openai/Qwen/Qwen2.5-7B-Instruct"
    chat_api_key: str | None = None
    chat_api_base: str | None = None
    chat_temperature: float = 0.2
    chat_max_tokens: int = 1024
    chat_max_context_chars: int = 12000

    rerank_enabled: bool = True
    rerank_model: str = "BAAI/bge-reranker-v2-m3"
    rerank_api_key: str | None = None
    rerank_api_base: str | None = None
    rerank_timeout_seconds: float = 30.0

    langfuse_enabled: bool = False
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"
    langfuse_environment: str = "development"
    langfuse_release: str = "local"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
