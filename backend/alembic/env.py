"""Alembic migration env.py（同步模式，仅 Alembic 使用）。

- 使用 ALEMBIC_DATABASE_URL（psycopg sync driver）
- 自动 import 所有 models 以确保 metadata 完整
- 同时支持 offline (alembic upgrade xxx.sql) 和 online 模式
"""

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# --- 将 backend/ 加入 path，以便 import app.models ---
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# --- 导入所有 models，让 Base.metadata 包含全部表 ---
# 依赖 backend/app/models/__init__.py 在批 3 中 re-export 所有 model 子模块
import app.models  # noqa: F401
from app.models.base import Base

# --- Alembic Config 对象 ---
config = context.config

# --- 从环境变量读取 sync 数据库 URL ---
alembic_url = os.getenv(
    "ALEMBIC_DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5432/postgres",
)
config.set_main_option("sqlalchemy.url", alembic_url)

# --- Logging ---
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# --- target_metadata 供 autogenerate 使用 ---
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Offline 模式：生成 SQL 脚本，不连接数据库。"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Online 模式：连接数据库执行迁移。"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
