"""v1 API 聚合路由：把各业务子路由挂到统一前缀下。"""

from fastapi import APIRouter

from app.api.v1.documents import list_router, upload_router
from app.api.v1.extraction import router as extraction_router
from app.api.v1.graph import router as graph_router
from app.api.v1.health import router as health_router
from app.api.v1.query import router as query_router

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(health_router)
v1_router.include_router(upload_router)
v1_router.include_router(list_router)
v1_router.include_router(extraction_router)
v1_router.include_router(graph_router)
v1_router.include_router(query_router)
