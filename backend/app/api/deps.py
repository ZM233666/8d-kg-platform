"""FastAPI 依赖：db session、neo4j driver、minio client。"""

from collections.abc import AsyncGenerator

from minio import Minio
from neo4j import AsyncDriver
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.neo4j import get_neo4j_driver
from app.db.postgres import async_session_maker
from app.services.minio_client import get_minio_client


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """提供 async db session，用完自动 close。"""
    session: AsyncSession = async_session_maker()
    try:
        yield session
    finally:
        await session.close()


async def get_neo4j() -> AsyncDriver:
    """提供 neo4j async driver（单例，由 lifespan 管理生命周期，不在此 close）。"""
    return get_neo4j_driver()


def get_minio() -> Minio:
    """提供 minio 单例 client。"""
    return get_minio_client()
