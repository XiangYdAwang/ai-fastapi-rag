import logging

from langfuse import Langfuse

from app.core.config import settings

logger = logging.getLogger(__name__)

_langfuse_client: Langfuse | None = None


def configure_observability() -> None:
    global _langfuse_client

    if not settings.langfuse_enabled:
        _langfuse_client = None
        logger.info("Langfuse tracing is disabled")
        return

    if not settings.langfuse_public_key:
        raise RuntimeError("LANGFUSE_PUBLIC_KEY is not configured")

    if not settings.langfuse_secret_key:
        raise RuntimeError("LANGFUSE_SECRET_KEY is not configured")

    _langfuse_client = Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
        environment=settings.langfuse_environment,
        release=settings.langfuse_release,
    )

    logger.info("Langfuse tracing enabled")


def get_observability_client() -> Langfuse | None:
    return _langfuse_client


def flush_observability() -> None:
    if _langfuse_client is None:
        return

    try:
        _langfuse_client.flush()
    except Exception:
        logger.exception("Failed to flush Langfuse traces")