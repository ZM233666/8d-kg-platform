"""Pipeline 异步任务定义。"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import UUID

import structlog

from app.core.config import settings
from app.tasks.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(
    name="app.tasks.pipeline_tasks.run_extraction_task",
    bind=True,
    max_retries=0,  # 失败不重试（pipeline 副作用复杂）
)
def run_extraction_task(
    self,
    document_id: str,
    extraction_run_id: str,
    pipeline_version: str = "v0.1.0",
) -> dict:
    """异步执行完整 pipeline (s1 → s6)。

    入参为字符串 UUID（Celery JSON 序列化需要），内部转 UUID。
    返回任务执行摘要 dict。
    Worker 内部用 asyncio.run 跑异步 pipeline。
    """
    logger.info(
        "task.run_extraction_task.start",
        task_id=self.request.id,
        document_id=document_id,
        extraction_run_id=extraction_run_id,
    )

    doc_uuid = UUID(document_id)
    run_uuid = UUID(extraction_run_id)

    try:
        result = asyncio.run(_run_pipeline_async(doc_uuid, run_uuid, pipeline_version))
        logger.info(
            "task.run_extraction_task.done",
            task_id=self.request.id,
            extraction_run_id=extraction_run_id,
            result=result,
        )
        return result
    except Exception as exc:
        logger.exception(
            "task.run_extraction_task.failed",
            task_id=self.request.id,
            extraction_run_id=extraction_run_id,
            error=str(exc),
        )
        # 把 extraction_run 标记为 failed（避免永远 pending）
        try:
            asyncio.run(_mark_run_failed(run_uuid, str(exc)))
        except Exception as inner:
            logger.error("task.mark_failed.also_failed", error=str(inner))
        raise


async def _run_pipeline_async(
    document_id: UUID,
    extraction_run_id: UUID,
    pipeline_version: str,
) -> dict:
    """实际异步逻辑：查 doc → 构造 ctx → run_pipeline。"""
    from sqlalchemy import select
    from app.db.postgres import async_session_maker
    from app.models.document import Document
    from app.pipeline.base import run_pipeline
    from app.pipeline.context import PipelineContext
    from app.pipeline.s1_parse import run as s1
    from app.pipeline.s2_split import run as s2
    from app.pipeline.s3_table import run as s3
    from app.pipeline.s4_extract import run as s4
    from app.pipeline.s5_vectorize import run as s5
    from app.pipeline.s6_write import run as s6

    # 查 document 拿 minio_key
    async with async_session_maker() as session:
        r = await session.execute(select(Document).where(Document.id == document_id))
        doc = r.scalar_one_or_none()
        if doc is None:
            raise RuntimeError(f"document not found: {document_id}")
        minio_key = doc.minio_key

    ctx = PipelineContext(
        document_id=document_id,
        minio_key=minio_key,
        report_id_hint=None,
        pipeline_version=pipeline_version,
        extraction_run_id=extraction_run_id,  # 关键：传 run_id，s6_write 后续走 UPDATE 分支
    )

    ctx = await run_pipeline(ctx, [s1, s2, s3, s4, s5, s6])

    return {
        "document_id": str(document_id),
        "extraction_run_id": str(extraction_run_id),
        "chunks": len(ctx.chunks),
        "stats": ctx.extraction_result.stats if ctx.extraction_result else None,
    }


async def _mark_run_failed(extraction_run_id: UUID, error: str) -> None:
    """task 抛异常时把 run 标记为 failed。"""
    from sqlalchemy import update
    from app.db.postgres import async_session_maker
    from app.models.extraction_run import ExtractionRun

    async with async_session_maker() as session:
        await session.execute(
            update(ExtractionRun)
            .where(ExtractionRun.id == extraction_run_id)
            .values(
                status="failed",
                finished_at=datetime.now(timezone.utc),
                error_detail={"error": error[:2000]},
            )
        )
        await session.commit()