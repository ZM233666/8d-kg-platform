"""提取任务相关路由：触发提取（异步）+ 查询 run 状态 + 列表。"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.llm import effective_llm_model
from app.models.document import Document
from app.models.extraction_run import ExtractionRun
from app.schemas.api import (
    ExtractionCancelResponse,
    ExtractionRunListResponse,
    ExtractionRunResponse,
    ExtractionTriggerResponse,
)
from app.services.extraction_run_service import mark_run_cancelled
from app.tasks.celery_app import celery_app

router = APIRouter(tags=["extraction"])


def _run_to_response(
    run: ExtractionRun, document_file_name: str | None = None
) -> ExtractionRunResponse:
    """ORM → API 响应，附带文档文件名。"""
    resp = ExtractionRunResponse.model_validate(run)
    if document_file_name is not None:
        return resp.model_copy(update={"document_file_name": document_file_name})
    return resp


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
    now = datetime.now(UTC)
    run = ExtractionRun(
        id=run_id,
        document_id=document_id,
        pipeline_version=pipeline_version,
        llm_model=effective_llm_model(),
        started_at=now,
        status="pending",
    )
    db.add(run)
    await db.commit()

    # 3. 入队 Celery task，记录 task id 供取消时 revoke
    async_result = await asyncio.to_thread(
        celery_app.send_task,
        "app.tasks.pipeline_tasks.run_extraction_task",
        args=[str(document_id), str(run_id), pipeline_version],
        ignore_result=True,
    )
    run.stage_metrics = {"celery_task_id": async_result.id}
    await db.commit()

    # 4. 立即返回 202
    return ExtractionTriggerResponse(
        run_id=run_id,
        document_id=document_id,
        status="pending",
        message="extraction queued; poll GET /api/v1/extraction-runs/{run_id} for status",
    )


@router.get(
    "/extraction-runs",
    response_model=ExtractionRunListResponse,
)
async def list_extraction_runs(
    document_id: UUID | None = Query(None, description="按 document_id 过滤"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> ExtractionRunListResponse:
    """列出 extraction runs（分页，可按 document_id 过滤）。"""
    base = select(ExtractionRun, Document.file_name).outerjoin(
        Document, ExtractionRun.document_id == Document.id
    )
    if document_id is not None:
        base = base.where(ExtractionRun.document_id == document_id)

    count_stmt = select(func.count()).select_from(ExtractionRun)
    if document_id is not None:
        count_stmt = count_stmt.where(ExtractionRun.document_id == document_id)
    total = (await db.execute(count_stmt)).scalar_one()

    items_result = await db.execute(
        base.order_by(ExtractionRun.started_at.desc()).offset(offset).limit(limit)
    )
    items = [_run_to_response(run, file_name) for run, file_name in items_result.all()]

    return ExtractionRunListResponse(items=items, total=total, offset=offset, limit=limit)


@router.get(
    "/extraction-runs/list",
    response_model=ExtractionRunListResponse,
    include_in_schema=False,
)
async def list_extraction_runs_legacy_alias(
    document_id: UUID | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> ExtractionRunListResponse:
    """兼容旧前端误调 GET /extraction-runs/list（应使用 GET /extraction-runs）。"""
    return await list_extraction_runs(document_id=document_id, offset=offset, limit=limit, db=db)


@router.post(
    "/extraction-runs/{run_id}/cancel",
    response_model=ExtractionCancelResponse,
)
async def cancel_extraction(
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> ExtractionCancelResponse:
    """取消 pending/running 的抽取任务。"""
    result = await db.execute(select(ExtractionRun).where(ExtractionRun.id == run_id))
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail=f"extraction run not found: {run_id}")

    if run.status not in ("pending", "running"):
        raise HTTPException(
            status_code=409,
            detail=f"cannot cancel run in status: {run.status}",
        )

    task_id = (run.stage_metrics or {}).get("celery_task_id")
    if task_id:
        await asyncio.to_thread(
            celery_app.control.revoke,
            task_id,
            terminate=True,
        )

    await mark_run_cancelled(db, run)

    return ExtractionCancelResponse(
        run_id=run_id,
        status="failed",
        message="extraction cancelled",
    )


@router.post(
    "/extraction-runs/{run_id}/retry",
    response_model=ExtractionTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_extraction(
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> ExtractionTriggerResponse:
    """重新触发抽取：failed 新建 run；pending 卡住时重新入队同一 run。"""
    result = await db.execute(select(ExtractionRun).where(ExtractionRun.id == run_id))
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail=f"extraction run not found: {run_id}")

    if run.status == "pending":
        async_result = await asyncio.to_thread(
            celery_app.send_task,
            "app.tasks.pipeline_tasks.run_extraction_task",
            args=[str(run.document_id), str(run.id), run.pipeline_version],
            ignore_result=True,
        )
        run.stage_metrics = {"celery_task_id": async_result.id, "requeued": True}
        run.finished_at = None
        run.error_detail = None
        await db.commit()
        return ExtractionTriggerResponse(
            run_id=run.id,
            document_id=run.document_id,
            status="pending",
            message="pending run requeued; ensure Celery worker is running (make worker)",
        )

    if run.status != "failed":
        raise HTTPException(
            status_code=409,
            detail=f"only failed or pending runs can be retried, got: {run.status}",
        )

    return await trigger_extraction(run.document_id, db)


@router.get(
    "/extraction-runs/{run_id}",
    response_model=ExtractionRunResponse,
)
async def get_extraction_run(
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> ExtractionRunResponse:
    """查询 extraction run 状态（pending / running / succeeded / failed）。"""
    result = await db.execute(
        select(ExtractionRun, Document.file_name)
        .outerjoin(Document, ExtractionRun.document_id == Document.id)
        .where(ExtractionRun.id == run_id)
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"extraction run not found: {run_id}")
    run, file_name = row
    return _run_to_response(run, file_name)
