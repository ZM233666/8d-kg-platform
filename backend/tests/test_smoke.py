"""冒烟测试：验证配置加载、模块导入、Base.metadata 表完整性。"""

import pytest

from app.core.config import settings


class TestSettings:
    def test_database_url_uses_asyncpg(self):
        """DATABASE_URL 必须包含 asyncpg 驱动。"""
        assert "asyncpg" in settings.database_url
        assert "@" in settings.database_url

    def test_alembic_database_url_uses_psycopg(self):
        """ALEMBIC_DATABASE_URL 必须使用 psycopg（同步）。"""
        assert "psycopg" in settings.alembic_database_url

    def test_redis_url_read_from_env(self):
        """REDIS_URL 从 .env 读取（不重建）。"""
        assert settings.redis_url.startswith("redis://")

    def test_pipeline_version_set(self):
        assert settings.pipeline.pipeline_version == "pipeline-v0.1.0"

    def test_jwt_expire_minutes(self):
        assert settings.jwt_expire_minutes == 1440


class TestModelImports:
    def test_import_document(self):
        from app.models import Document

        assert Document.__tablename__ == "documents"

    def test_import_chunk(self):
        from app.models import Chunk

        assert Chunk.__tablename__ == "chunks"

    def test_import_extraction_run(self):
        from app.models import ExtractionRun

        assert ExtractionRun.__tablename__ == "extraction_runs"

    def test_import_audit_log(self):
        from app.models import AuditLog

        assert AuditLog.__tablename__ == "audit_logs"

    def test_import_user(self):
        from app.models import User

        assert User.__tablename__ == "users"

    def test_import_base(self):
        from app.models import Base

        assert hasattr(Base, "metadata")


class TestBaseMetadata:
    def test_tables_include_documents(self):
        from app.models import Base

        assert "documents" in Base.metadata.tables

    def test_tables_include_chunks(self):
        from app.models import Base

        assert "chunks" in Base.metadata.tables

    def test_tables_include_extraction_runs(self):
        from app.models import Base

        assert "extraction_runs" in Base.metadata.tables

    def test_tables_include_audit_logs(self):
        from app.models import Base

        assert "audit_logs" in Base.metadata.tables

    def test_tables_include_users(self):
        from app.models import Base

        assert "users" in Base.metadata.tables

    def test_all_required_tables_present(self):
        from app.models import Base

        required = {"documents", "chunks", "extraction_runs", "audit_logs", "users"}
        actual = set(Base.metadata.tables.keys())
        missing = required - actual
        assert not missing, f"Missing tables in Base.metadata: {missing}"
