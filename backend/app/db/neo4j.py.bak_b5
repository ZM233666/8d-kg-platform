"""Neo4j async driver（neo4j Python driver）。"""

from neo4j import AsyncGraphDatabase, AsyncDriver

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

_neo4j_driver: AsyncDriver | None = None


def get_neo4j_driver() -> AsyncDriver:
    """获取全局 Neo4j async driver（延迟初始化）。"""
    global _neo4j_driver
    if _neo4j_driver is None:
        _neo4j_driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
            max_connection_lifetime=3600,
        )
    return _neo4j_driver


async def close_neo4j_driver() -> None:
    """关闭 driver。"""
    global _neo4j_driver
    if _neo4j_driver is not None:
        await _neo4j_driver.close()
        _neo4j_driver = None


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
