"""正式 e2e: committed docx fixture -> mock 抽取 -> PG/Neo4j 写入 -> 查询回看。"""

from __future__ import annotations

import socket
import uuid
from pathlib import Path

import pytest
from app.core.config import settings
from app.db.neo4j import get_neo4j_driver
from app.db.postgres import async_session_maker
from app.models.chunk import Chunk as ChunkModel
from app.models.document import Document
from app.models.extraction_run import ExtractionRun
from app.pipeline.context import PipelineContext
from app.pipeline.s1_parse import run as s1_run
from app.pipeline.s2_split import run as s2_run
from app.pipeline.s4_extract import run as s4_run
from app.pipeline.s6_write import run as s6_run
from app.services.query_service import search
from sqlalchemy import func, select

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MOCK_DOCX = PROJECT_ROOT / "backend" / "tests" / "fixtures" / "mock_8d_report.docx"


def _port_open(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


@pytest.mark.asyncio
@pytest.mark.integration
async def test_mock_fixture_pipeline_e2e() -> None:
    assert MOCK_DOCX.exists(), f"missing committed fixture docx: {MOCK_DOCX}"

    missing_services = [
        name
        for name, port in (
            ("postgres", 5432),
            ("neo4j", 7687),
        )
        if not _port_open(port)
    ]
    if missing_services:
        pytest.skip(f"missing integration services: {', '.join(missing_services)}")

    original_provider = settings.llm_provider
    original_fallback = settings.llm_fallback_provider
    settings.llm_provider = "mock"
    settings.llm_fallback_provider = None

    try:
        ctx = PipelineContext(
            document_id=uuid.uuid4(),
            minio_key=f"local://{MOCK_DOCX}",
            report_id_hint="MOCK-E2E",
        )
        ctx = await s1_run(ctx)
        ctx = await s2_run(ctx)
        ctx = await s4_run(ctx)
        ctx = await s6_run(ctx)

        assert ctx.extraction_result is not None
        assert ctx.extraction_run_id is not None
        assert ctx.extraction_result.report is not None
        assert ctx.extraction_result.report.business_key == "FS-2024-001"

        async with async_session_maker() as session:
            run_row = await session.scalar(
                select(ExtractionRun).where(ExtractionRun.id == ctx.extraction_run_id)
            )
            assert run_row is not None
            assert str(run_row.status) == "succeeded"

            document_row = await session.scalar(
                select(Document).where(Document.id == run_row.document_id)
            )
            assert document_row is not None
            assert document_row.file_name == MOCK_DOCX.name

            chunk_count = await session.scalar(
                select(func.count())
                .select_from(ChunkModel)
                .where(
                    ChunkModel.document_id == run_row.document_id,
                    ChunkModel.chunk_business_key == ctx.chunks[0].chunk_id,
                )
            )
            assert len(ctx.chunks) == 1
            assert int(chunk_count or 0) == 1

        driver = get_neo4j_driver()
        async with driver.session() as neo_session:
            result = await neo_session.run(
                """
                MATCH (r:EightDReport {business_key: $report_key})
                OPTIONAL MATCH (e:ProductEvent)-[:HAS_8D_REPORT]->(r)
                OPTIONAL MATCH (r)-[:ROOT_CAUSE]->(c:CauseItem)
                OPTIONAL MATCH (r)-[:CORRECTIVE_ACTION|PREVENTIVE_ACTION]->(a:ActionItem)
                OPTIONAL MATCH (r)-[:AFFECTED_SERIAL]->(:PartSerial)-[:SUPPLIED_BY]->(o:Organization)
                RETURN r.business_key AS business_key,
                       r.issue_title AS issue_title,
                       r.filename AS filename,
                       e.business_key AS event_key,
                       e.occurred_at AS occurred_at,
                       count(DISTINCT c) AS cause_count,
                       count(DISTINCT a) AS action_count,
                       collect(DISTINCT a.action_id) AS action_ids,
                       collect(DISTINCT o.business_key) AS supplier_org_keys
                """,
                {"report_key": "FS-2024-001"},
            )
            row = await result.single()

        assert row is not None
        assert row["business_key"] == "FS-2024-001"
        assert row["issue_title"] == "EP2002 阀门出厂测试密封面泄漏"
        assert row["filename"] == MOCK_DOCX.name
        assert row["event_key"] == "EVT-FS-2024-001"
        assert str(row["occurred_at"]).startswith("2026-04-10")
        assert row["cause_count"] == 1
        assert row["action_count"] == 3
        assert set(row["action_ids"]) == {
            "ACT-FS-2024-001-1",
            "ACT-FS-2024-001-2",
            "ACT-FS-2024-001-3",
        }
        assert "ORG-SUZ-SEAL" in row["supplier_org_keys"]

        async with async_session_maker() as session:
            search_items = await search(
                driver=driver,
                db=session,
                query="FS-2024-001",
                top_k=5,
            )
        assert any(
            item["entity_type"] == "EightDReport" and item["id"] == "FS-2024-001"
            for item in search_items
        )

    finally:
        settings.llm_provider = original_provider
        settings.llm_fallback_provider = original_fallback
