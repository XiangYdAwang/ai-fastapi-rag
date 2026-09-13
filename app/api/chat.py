from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_service import answer_question, stream_answer

router = APIRouter(
    prefix="/api",
    tags=["chat"],
)


@router.post(
    "/chat",
    response_model=ChatResponse,
)
async def chat_endpoint(
    request: ChatRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ChatResponse:
    return await answer_question(request=request, db=db)


@router.post(
    "/chat/stream",
    response_class=StreamingResponse,
)
async def chat_stream_endpoint(
    request: ChatRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StreamingResponse:
    return StreamingResponse(
        stream_answer(request=request, db=db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )