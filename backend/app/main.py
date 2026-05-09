"""FastAPI 应用入口：lifespan / 路由注册 / 异常处理。"""

import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.v1.routes_health import router as health_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import get_logger, setup_logging
from app.db.minio import ensure_minio_bucket, ping_minio
from app.db.neo4j import close_neo4j_driver, get_neo4j_driver, ping_neo4j
from app.db.postgres import async_engine
from app.db.redis import close_redis_client, ping_redis

log = get_logger(__name__)


# -------------------------------------------------------------------
# Lifespan：启动时初始化，关闭时清理
# -------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """应用生命周期管理。"""
    setup_logging()
    log.info("app_starting", version=settings.pipeline.pipeline_version)

    # --- MinIO bucket 初始化（确保写入目标存在）---
    try:
        ensure_minio_bucket()
    except Exception as e:
        log.error("minio_bucket_init_failed", error=str(e))
        if settings.strict_startup:
            raise RuntimeError("MinIO bucket initialization failed") from e

    # --- 深度健康检查 ---
    pg_ok = await _ping_postgres()
    neo4j_ok = await ping_neo4j()
    redis_ok = await ping_redis()
    minio_ok = await ping_minio()

    all_ok = pg_ok and neo4j_ok and redis_ok and minio_ok

    if not all_ok:
        log.warning(
            "app_started_with_degraded_dependencies",
            postgres=pg_ok,
            neo4j=neo4j_ok,
            redis=redis_ok,
            minio=minio_ok,
        )
        if settings.strict_startup:
            raise RuntimeError(
                f"Startup failed: postgres={pg_ok}, neo4j={neo4j_ok}, "
                f"redis={redis_ok}, minio={minio_ok}"
            )

    yield

    # --- 关闭 ---
    await close_neo4j_driver()
    await close_redis_client()
    await async_engine.dispose()
    log.info("app_shutdown_complete")


async def _ping_postgres() -> bool:
    from sqlalchemy import text

    try:
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        log.error("postgres_ping_failed", error=str(e))
        return False


# -------------------------------------------------------------------
# FastAPI 实例
# -------------------------------------------------------------------

app = FastAPI(
    title="8D KG Platform API",
    version=settings.pipeline.pipeline_version,
    openapi_url="/api/v1/openapi.json",
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    lifespan=lifespan,
)

# --- Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TraceIdMiddleware(BaseHTTPMiddleware):
    """为每个请求注入 trace_id 到 request.state。"""

    async def dispatch(self, request: Request, call_next):
        trace_id = request.headers.get("X-Trace-Id", str(uuid.uuid4()))
        request.state.trace_id = trace_id
        response = await call_next(request)
        response.headers["X-Trace-Id"] = trace_id
        return response


app.add_middleware(TraceIdMiddleware)

# --- 异常处理 ---
register_exception_handlers(app)

# --- 路由 ---
app.include_router(health_router, tags=["Health"])


# -------------------------------------------------------------------
# 尚待实现的路由（v0.2+）将在后续批添加
# -------------------------------------------------------------------
