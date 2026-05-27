"""pytest 全局 fixtures。"""

import asyncio
from collections.abc import AsyncGenerator
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# 需要在导入任何 app 模块前设置 event loop policy
pytest_plugins = ["pytest_asyncio"]


@pytest.fixture(scope="session")
def event_loop_policy():
    return asyncio.get_event_loop_policy()


# -------------------------------------------------------------------
# Settings fixture：覆盖 .env 中的数据库 URL 指向 test schema
# -------------------------------------------------------------------


@pytest.fixture
def mock_settings():
    """返回一个只读的 mock settings，避免真实连接。"""
    from app.core.config import Settings

    s = MagicMock(spec=Settings)
    s.database_url = "postgresql+asyncpg://test:test@localhost:5432/test"
    s.alembic_database_url = "postgresql+psycopg://test:test@localhost:5432/test"
    s.redis_url = "redis://localhost:6379/15"
    s.celery_broker_url = "redis://localhost:6379/16"
    s.celery_result_backend = "redis://localhost:6379/17"
    s.minio_endpoint = "localhost:9000"
    s.minio_access_key = "testkey"
    s.minio_secret_key = "testsecret"
    s.minio_bucket = "kg-test"
    s.minio_secure = False
    s.neo4j_uri = "bolt://localhost:7687"
    s.neo4j_user = "neo4j"
    s.neo4j_password = "neo4j"
    s.neo4j_database = "neo4j"
    s.pipeline.pipeline_version = "pipeline-v0.1.0"
    s.pipeline.schema_version = "v0.1.0"
    s.debug = False
    s.log_level = "WARNING"
    s.strict_startup = False
    s.cors_allowed_origins = ["http://localhost:5173"]
    return s


# -------------------------------------------------------------------
# Async engine / session fixtures（需要真实 DB 时启用）
# -------------------------------------------------------------------


@pytest.fixture
async def async_engine(mock_settings):
    """创建测试用 async engine（生产环境替换为 testcontainers）。"""
    engine = create_async_engine(
        mock_settings.database_url,
        echo=False,
        pool_pre_ping=True,
    )
    yield engine
    await engine.dispose()


@pytest.fixture
async def async_session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    """每个 test 创建一个 session，测试结束后 rollback。"""
    async_session_maker = async_sessionmaker(
        bind=async_engine,
        expire_on_commit=False,
        autoflush=False,
        class_=AsyncSession,
    )
    async with async_session_maker() as session:
        yield session
        await session.rollback()
