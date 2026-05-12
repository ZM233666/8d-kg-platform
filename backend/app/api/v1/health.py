"""四件套健康检查：PostgreSQL / Neo4j / Redis / MinIO。"""

import asyncio

from fastapi import APIRouter, status, Response
from sqlalchemy import text

from app.db.postgres import async_session_maker
from app.db.neo4j import get_neo4j_driver
from app.services.minio_client import get_minio_client
from app.core.config import settings
import structlog

import redis.asyncio as aioredis

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


async def _ping_postgres() -> str:
    try:
        async with async_session_maker() as session:
            await session.execute(text("SELECT 1"))
        return "ok"
    except Exception as e:
        logger.warning("health_pg_failed", error=str(e))
        return f"fail:{e}"


async def _ping_neo4j() -> str:
    try:
        driver = get_neo4j_driver()
        async with driver.session() as session:
            result = await session.run("RETURN 1 AS n")
            await result.single()
        return "ok"
    except Exception as e:
        logger.warning("health_neo4j_failed", error=str(e))
        return f"fail:{e}"


async def _ping_redis() -> str:
    try:
        client = await aioredis.from_url(
            settings.redis_url,
            encoding="utf8",
            decode_responses=True,
        )
        await client.ping()
        await client.aclose()
        return "ok"
    except Exception as e:
        logger.warning("health_redis_failed", error=str(e))
        return f"fail:{e}"


async def _ping_minio() -> str:
    try:
        client = get_minio_client()

        def _list_buckets():
            client.list_buckets()

        await asyncio.to_thread(_list_buckets)
        return "ok"
    except Exception as e:
        logger.warning("health_minio_failed", error=str(e))
        return f"fail:{e}"


@router.get("")
async def health(response: Response) -> dict[str, str]:
    """
    并行健康检查四件套。
    全部 ok → 200，任一 fail → 503。
    """
    async def _with_timeout(coro, name):
        try:
            return await asyncio.wait_for(coro, timeout=2.0)
        except BaseException as e:
            # 捕获一切：TimeoutError / CancelledError / 业务异常
            logger.warning(f"health_{name}_failed", error=str(e))
            return f"fail:{e}"

    pg, neo4j, redis_res, minio = await asyncio.gather(
        _with_timeout(_ping_postgres(), "pg"),
        _with_timeout(_ping_neo4j(), "neo4j"),
        _with_timeout(_ping_redis(), "redis"),
        _with_timeout(_ping_minio(), "minio"),
    )

    results = {
        "db": pg,
        "neo4j": neo4j,
        "redis": redis_res,
        "minio": minio,
    }

    all_ok = all(v == "ok" for v in results.values())
    if not all_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return results
