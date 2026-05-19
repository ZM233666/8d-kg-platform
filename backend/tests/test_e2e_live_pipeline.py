"""真实服务 e2e: docx -> Codex 抽取 -> PG/Neo4j 写入 -> 查询回看。"""

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
EP2002_DOCX = (
    PROJECT_ROOT
    / "docs_for_test"
    / "8D_EP2002阀Secondary regulator out of range故障调查报告_01.docx"
)


def _port_open(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


@pytest.mark.asyncio
@pytest.mark.integration
async def test_ep2002_live_pipeline_e2e() -> None:
    if not EP2002_DOCX.exists():
        pytest.skip(f"missing sample docx: {EP2002_DOCX}")

    missing_services = [
        name
        for name, port in (
            ("postgres", 5432),
            ("neo4j", 7687),
            ("codex-service", 8787),
        )
        if not _port_open(port)
    ]
    if missing_services:
        pytest.skip(f"missing live services: {', '.join(missing_services)}")

    original_provider = settings.llm_provider
    original_fallback = settings.llm_fallback_provider
    original_retries = settings.codex_max_retries

    settings.llm_provider = "codex"
    settings.llm_fallback_provider = None
    settings.codex_max_retries = max(settings.codex_max_retries, 4)

    try:
        ctx = PipelineContext(
            document_id=uuid.uuid4(),
            minio_key=f"local://{EP2002_DOCX}",
            report_id_hint="EP2002-REAL-SMOKE",
        )
        ctx = await s1_run(ctx)
        ctx = await s2_run(ctx)
        ctx = await s4_run(ctx)
        ctx = await s6_run(ctx)

        assert ctx.extraction_result is not None
        assert ctx.extraction_run_id is not None
        assert ctx.extraction_result.report is not None

        report_key = ctx.extraction_result.report.business_key
        assert report_key == "EP2002-REAL-SMOKE"

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
            assert document_row.file_name == EP2002_DOCX.name

            chunk_count = await session.scalar(
                select(func.count())
                .select_from(ChunkModel)
                .where(ChunkModel.document_id == run_row.document_id)
            )
            assert int(chunk_count or 0) == len(ctx.chunks) == 18

        driver = get_neo4j_driver()
        async with driver.session() as neo_session:
            report_result = await neo_session.run(
                """
                MATCH (r:EightDReport {business_key: $report_key})
                OPTIONAL MATCH (e:ProductEvent)-[:HAS_8D_REPORT]->(r)
                RETURN r.business_key AS business_key,
                       r.issue_title AS issue_title,
                       r.owner_name AS owner_name,
                       r.closed_at AS closed_at,
                       e.occurred_at AS occurred_at
                """,
                {"report_key": report_key},
            )
            report_row = await report_result.single()
            assert report_row is not None
            assert report_row["business_key"] == report_key
            assert report_row["owner_name"] is None
            assert report_row["closed_at"] is None
            assert report_row["occurred_at"] == "2022-08-19T00:00:00Z"

            action_result = await neo_session.run(
                """
                MATCH (r:EightDReport {business_key: $report_key})-[:CORRECTIVE_ACTION|PREVENTIVE_ACTION]->(a:ActionItem)
                OPTIONAL MATCH (a)-[:RESPONSIBLE_ORG]->(o:Organization)
                RETURN a.action_id AS action_id,
                       a.completed_at AS completed_at,
                       a.due_date AS due_date,
                       o.business_key AS org_key
                ORDER BY action_id
                """,
                {"report_key": report_key},
            )
            action_rows = [dict(row) async for row in action_result]

            report_org_result = await neo_session.run(
                """
                MATCH (r:EightDReport {business_key: $report_key})-[:RESPONSIBLE_ORG]->(o:Organization)
                RETURN o.business_key AS org_key
                """,
                {"report_key": report_key},
            )
            report_org_rows = [dict(row) async for row in report_org_result]

        edge_map = {row["action_id"]: row["org_key"] for row in action_rows if row["org_key"]}
        assert edge_map["ACT-2"] == "供应商"
        assert edge_map["ACT-3"] == "ORG-KB-SUZHOU"
        assert edge_map["ACT-4"] == "供应商"
        assert report_org_rows == []
        assert all(row["completed_at"] is None for row in action_rows)

        async with async_session_maker() as session:
            search_items = await search(
                driver=driver,
                db=session,
                query="克诺尔苏州",
                top_k=5,
            )
        assert any(
            item["entity_type"] == "ActionItem" and item["id"] == "ACT-3" for item in search_items
        )

    finally:
        settings.llm_provider = original_provider
        settings.llm_fallback_provider = original_fallback
        settings.codex_max_retries = original_retries
