"""Extraction run 取消 / 重试辅助逻辑。"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.extraction_run import ExtractionRun


class RunCancelledError(Exception):
    """任务已被用户取消。"""


async def assert_run_not_cancelled(extraction_run_id: UUID) -> None:
    """Pipeline 入口检查：若 run 已标记取消则中止。"""
    from app.db.postgres import async_session_maker

    async with async_session_maker() as session:
        result = await session.execute(
            select(ExtractionRun.status, ExtractionRun.error_detail).where(
                ExtractionRun.id == extraction_run_id
            )
        )
        row = result.one_or_none()
        if row is None:
            raise RunCancelledError("extraction run not found")
        status, error_detail = row
        if status == "failed" and (error_detail or {}).get("cancelled"):
            raise RunCancelledError("cancelled by user")


async def mark_run_cancelled(db: AsyncSession, run: ExtractionRun) -> ExtractionRun:
    """将 run 标记为用户取消（status=failed + error_detail.cancelled）。"""
    now = datetime.now(timezone.utc)
    run.status = "failed"
    run.finished_at = now
    run.error_detail = {
        "cancelled": True,
        "message": "用户取消",
    }
    await db.commit()
    await db.refresh(run)
    return run


def mark_run_running_sync(extraction_run_id: UUID, *, stage: str = "pipeline") -> None:
    """Worker 领取任务后立即标记为 running（避免长时间显示「等待中」）。"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.core.config import settings

    now = datetime.now(timezone.utc)
    engine = create_engine(settings.alembic_database_url, future=True)
    with Session(engine) as session:
        run = session.get(ExtractionRun, extraction_run_id)
        if run is None or run.status not in ("pending", "running"):
            return
        metrics = dict(run.stage_metrics or {})
        metrics["current_stage"] = stage
        session.execute(
            update(ExtractionRun)
            .where(ExtractionRun.id == extraction_run_id)
            .values(
                status="running",
                started_at=run.started_at or now,
                stage_metrics=metrics,
                finished_at=None,
                error_detail=None,
            )
        )
        session.commit()


def merge_celery_task_id_sync(extraction_run_id: UUID, celery_task_id: str) -> None:
    """Worker 启动时写入 Celery task id（同步，供 revoke 使用）。"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.core.config import settings

    engine = create_engine(settings.alembic_database_url, future=True)
    with Session(engine) as session:
        run = session.get(ExtractionRun, extraction_run_id)
        if run is None:
            return
        metrics = dict(run.stage_metrics or {})
        metrics["celery_task_id"] = celery_task_id
        session.execute(
            update(ExtractionRun)
            .where(ExtractionRun.id == extraction_run_id)
            .values(stage_metrics=metrics)
        )
        session.commit()
