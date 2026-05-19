"""语义/关键词检索端点。"""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends
from neo4j import AsyncDriver
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_neo4j
from app.services.query_service import search, structured_query

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


class StructuredQueryFilters(BaseModel):
    report_date_from: datetime | None = None
    report_date_to: datetime | None = None
    closed_at_from: datetime | None = None
    closed_at_to: datetime | None = None
    occurred_at_from: datetime | None = None
    occurred_at_to: datetime | None = None
    completed_at_from: datetime | None = None
    completed_at_to: datetime | None = None
    report_status: str | None = None
    event_type: str | None = None
    severity: str | None = None
    action_status: str | None = None
    action_type: str | None = None


class StructuredQueryRequest(BaseModel):
    entity_type: Literal["EightDReport", "ProductEvent", "ActionItem"]
    filters: StructuredQueryFilters = Field(default_factory=StructuredQueryFilters)
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
    sort_by: Literal[
        "report_date",
        "closed_at",
        "occurred_at",
        "completed_at",
        "created_at",
        "updated_at",
    ] = "updated_at"
    sort_order: Literal["asc", "desc"] = "desc"


class StructuredQueryItem(BaseModel):
    business_key: str | None
    entity_type: str
    summary: dict
    confidence: float | None = None
    source_doc_id: str | None = None


class StructuredQueryResponse(BaseModel):
    entity_type: str
    items: list[StructuredQueryItem]
    pagination: dict
    query_metrics: dict


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


@router.post("/structured", response_model=StructuredQueryResponse)
async def query_structured(
    body: StructuredQueryRequest,
    driver: AsyncDriver = Depends(get_neo4j),
) -> StructuredQueryResponse:
    """最小结构化查询：支持 EightDReport / ProductEvent 的时间范围过滤。"""
    result = await structured_query(
        driver=driver,
        entity_type=body.entity_type,
        filters=body.filters.model_dump(mode="json", exclude_none=True),
        page=body.page,
        page_size=body.page_size,
        sort_by=body.sort_by,
        sort_order=body.sort_order,
    )
    return StructuredQueryResponse(
        entity_type=result["entity_type"],
        items=[StructuredQueryItem(**item) for item in result["items"]],
        pagination=result["pagination"],
        query_metrics=result["query_metrics"],
    )


@router.get("/history", response_model=QueryHistoryResponse)
async def query_history(limit: int = 20) -> QueryHistoryResponse:
    """查询历史由前端本地存储；后端占位返回空列表。"""
    _ = limit
    return QueryHistoryResponse(items=[])
