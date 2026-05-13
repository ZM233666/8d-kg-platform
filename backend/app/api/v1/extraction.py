"""Extraction 异步触发 / 状态查询端点。"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.document import Document
from app.models.extraction_run import ExtractionRun
from app.pipeline.base import run_pipeline
from app.pipeline.context import PipelineContext
from app.pipeline.s1_parse import run as s1
from app.pipeline.s2_split import run as s2
from app.pipeline.s3_table import run as s3
from app.pipeline.s4_extract import run as s4
from app.pipeline.s5_vectorize import run as s5
from app.pipeline.s6_write import run as s6
from app.schemas.api import ExtractionRunResponse, ExtractionTriggerResponse

router = APIRouter(tags=["extraction"])


@router.post("/documents/{document_id}/extract", response_model=ExtractionTriggerResponse)
async def trigger_extraction(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> ExtractionTriggerResponse:
    """根据 document_id 触发 8D pipeline（s1→s6）。"""
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(404, "document not found")

    try:
        ctx = PipelineContext(
            document_id=doc.id,
            minio_key=doc.minio_key,
            report_id_hint=None,
            pipeline_version="v0.1.0",
        )
        ctx = await run_pipeline(ctx, [s1, s2, s3, s4, s5, s6])
        run_id = ctx.extraction_run_id
    except Exception as e:
        raise HTTPException(500, detail=str(e)) from e

    await db.commit()

    run_result = await db.execute(select(ExtractionRun).where(ExtractionRun.id == run_id))
    run = run_result.scalar_one_or_none()

    return ExtractionTriggerResponse(
        run_id=run_id,
        document_id=doc.id,
        status=run.status if run else "unknown",
    )


@router.get("/extraction-runs/{run_id}", response_model=ExtractionRunResponse)
async def get_extraction_run(
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> ExtractionRunResponse:
    """根据 run_id 查询 extraction run 详情。"""
    result = await db.execute(select(ExtractionRun).where(ExtractionRun.id == run_id))
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(404, "extraction run not found")
    return ExtractionRunResponse.model_validate(run)
