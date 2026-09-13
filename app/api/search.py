from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.search import SearchRequest, SearchResponse
from app.services.search_service import search_documents

router = APIRouter(
    prefix="/api",
    tags=["search"],
)


@router.post(
    "/search",
    response_model=SearchResponse,
)
async def search_documents_endpoint(
    request: SearchRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SearchResponse:
    return await search_documents(request=request, db=db)