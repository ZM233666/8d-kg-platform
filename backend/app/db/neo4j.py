"""Neo4j async driver（按 event loop 缓存）。"""

import asyncio

from neo4j import AsyncDriver, AsyncGraphDatabase

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

_drivers: dict[int, AsyncDriver] = {}


def get_neo4j_driver() -> AsyncDriver:
    """获取当前 event loop 对应的 Neo4j driver。"""
    loop = asyncio.get_running_loop()
    key = id(loop)

    if key not in _drivers:
        _drivers[key] = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
            max_connection_lifetime=3600,
        )

    return _drivers[key]


async def close_neo4j_driver() -> None:
    """关闭全部 driver。"""
    global _drivers

    for driver in _drivers.values():
        await driver.close()

    _drivers = {}


async def ping_neo4j() -> bool:
    """检查 Neo4j 连通性。"""
    try:
        driver = get_neo4j_driver()
        async with driver.session(database=settings.neo4j_database) as session:
            await session.run("RETURN 1")
        return True
    except Exception as e:
        log.error("neo4j_ping_failed", error=str(e))
        return False
