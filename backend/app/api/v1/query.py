"""语义/关键词检索端点。"""

from fastapi import APIRouter, Depends
from neo4j import AsyncDriver
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_neo4j
from app.services.query_service import search

router = APIRouter(prefix="/query", tags=["query"])


class QuerySearchRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    query: str = Field(..., min_length=1, description="检索关键词")
    top_k: int = Field(10, ge=1, le=50, alias="topK", description="返回条数上限")


class SearchResultItem(BaseModel):
    id: str
    content: str
    entity_type: str
    match_score: float
    timestamp: str


class QuerySearchResponse(BaseModel):
    items: list[SearchResultItem]


class QueryHistoryResponse(BaseModel):
    items: list[dict] = Field(default_factory=list)


@router.post("/search", response_model=QuerySearchResponse)
async def query_search(
    body: QuerySearchRequest,
    db: AsyncSession = Depends(get_db),
    driver: AsyncDriver = Depends(get_neo4j),
) -> QuerySearchResponse:
    """关键词检索（Neo4j 实体 + PG 文档块）。向量检索接入后在此扩展。"""
    results = await search(
        driver=driver,
        db=db,
        query=body.query.strip(),
        top_k=body.top_k,
    )
    return QuerySearchResponse(
        items=[SearchResultItem(**r) for r in results],
    )


@router.get("/history", response_model=QueryHistoryResponse)
async def query_history(limit: int = 20) -> QueryHistoryResponse:
    """查询历史由前端本地存储；后端占位返回空列表。"""
    _ = limit
    return QueryHistoryResponse(items=[])
