"""FastAPI 依赖注入：db session、neo4j driver、redis、minio、current_user。"""

from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Annotated

from fastapi import Depends, Request
from minio import Minio
from neo4j import AsyncDriver
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.minio import minio_client
from app.db.neo4j import get_neo4j_driver as _get_neo4j_driver
from app.db.postgres import get_db_session
from app.db.redis import redis_client

# 直接 re-export，给 FastAPI Depends 使用
DBSession = Annotated[AsyncSession, Depends(get_db_session)]


async def get_neo4j_driver() -> AsyncGenerator[AsyncDriver, None]:
    """异步 Neo4j driver。"""
    yield _get_neo4j_driver()


async def get_redis() -> AsyncGenerator[Redis, None]:
    """异步 Redis 客户端。"""
    yield redis_client


def get_minio() -> Minio:
    """MinIO 同步客户端（minio SDK 无原生 async）。"""
    return minio_client


# -------------------------------------------------------------------
# v0.1 用户占位：后续替换为 JWT 解析后的真实用户模型
# -------------------------------------------------------------------


class _PlaceholderUser:
    """v0.1 临时用户对象，仅含 user_id / role。"""

    def __init__(self, user_id: str = "u-placeholder", role: str = "user"):
        self.user_id = user_id
        self.role = role
        self.created_at = datetime.utcnow()


async def get_current_user(
    request: Request,
) -> _PlaceholderUser:
    """
    v0.1：从请求头解析当前用户（占位实现）。

    后续替换为：
    1. 从 Authorization: Bearer <token> 解析 JWT
    2. 验证 token 有效性
    3. 从 token claims 构造真实 User 对象
    """
    return _PlaceholderUser()


# 类型别名，供 API 路由使用
CurrentUser = Annotated[_PlaceholderUser, Depends(get_current_user)]
Neo4jDriver = Annotated[AsyncDriver, Depends(get_neo4j_driver)]
RedisClient = Annotated[Redis, Depends(get_redis)]
MinioClient = Annotated[Minio, Depends(get_minio)]
