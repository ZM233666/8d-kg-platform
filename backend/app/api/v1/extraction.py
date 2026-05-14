"""提取任务相关路由：触发提取（异步）+ 查询 run 状态。"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.document import Document
from app.models.extraction_run import ExtractionRun
from app.schemas.api import ExtractionRunResponse, ExtractionTriggerResponse
from app.tasks.celery_app import celery_app

router = APIRouter(tags=["extraction"])


@router.post(
    "/documents/{document_id}/extract",
    response_model=ExtractionTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_extraction(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> ExtractionTriggerResponse:
    """触发文档提取（异步）：INSERT extraction_run(status='pending') → 入队 Celery → 立即返回 202 + run_id。"""
    # 1. 验证 document 存在
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail=f"document not found: {document_id}")

    # 2. INSERT extraction_runs(status='pending')
    run_id = uuid4()
    pipeline_version = "v0.1.0"
    now = datetime.now(timezone.utc)
    run = ExtractionRun(
        id=run_id,
        document_id=document_id,
        pipeline_version=pipeline_version,
        llm_model="mock-v0.1",
        started_at=now,
        status="pending",
    )
    db.add(run)
    await db.commit()

    # 3. 入队 Celery task（fire-and-forget，跳过 result backend ack 等待）
    await asyncio.to_thread(
        celery_app.send_task,
        "app.tasks.pipeline_tasks.run_extraction_task",
        args=[str(document_id), str(run_id), pipeline_version],
        ignore_result=True,
    )

    # 4. 立即返回 202
    return ExtractionTriggerResponse(
        run_id=run_id,
        document_id=document_id,
        status="pending",
        message="extraction queued; poll GET /api/v1/extraction-runs/{run_id} for status",
    )


@router.get(
    "/extraction-runs/{run_id}",
    response_model=ExtractionRunResponse,
)
async def get_extraction_run(
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> ExtractionRun:
    """查询 extraction run 状态（pending / running / succeeded / failed）。"""
    result = await db.execute(select(ExtractionRun).where(ExtractionRun.id == run_id))
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail=f"extraction run not found: {run_id}")
    return run