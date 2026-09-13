from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from sqlalchemy import text

from app.api.documents import router as documents_router
from app.core.config import settings
from app.db.session import engine

from app.api.search import router as search_router
from app.api.chat import router as chat_router

from app.core.observability import (
    configure_observability,
    flush_observability,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_observability()

    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)

    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))

    yield

    flush_observability()
    await engine.dispose()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(documents_router)
app.include_router(search_router)
app.include_router(chat_router)

@app.get("/")
async def root():
    return {"message": "AI FastAPI service is running"}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/health/db")
async def health_db():
    async with engine.connect() as connection:
        result = await connection.execute(text("SELECT version()"))

    return {"database": result.scalar_one()}



# 启动时检查数据库；
# 自动创建 data/uploads；
# 注册文档上传路由。

