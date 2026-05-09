"""Redis async client（redis.asyncio）。"""

from redis.asyncio import Redis, from_url

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

_redis_client: Redis | None = None


def get_redis_client() -> Redis:
    """获取全局 Redis async client。"""
    global _redis_client
    if _redis_client is None:
        _redis_client = from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=20,
        )
    return _redis_client


async def close_redis_client() -> None:
    """关闭 Redis client。"""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None


async def ping_redis() -> bool:
    """检查 Redis 连通性。"""
    try:
        client = get_redis_client()
        await client.ping()
        return True
    except Exception as e:
        log.error("redis_ping_failed", error=str(e))
        return False


# 供 deps.py 直接引用
redis_client = get_redis_client()
