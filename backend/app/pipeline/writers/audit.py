"""Audit Writer：将 pipeline 完成摘要写入 audit_logs 表。"""

from __future__ import annotations

import json
import structlog
from uuid import UUID
from datetime import datetime

from app.db.postgres import async_session_maker
from app.models import AuditLog
from app.pipeline.context import PipelineContext

logger = structlog.get_logger(__name__)


class _UUIDEncoder(json.JSONEncoder):
    """JSON 编码器，支持 UUID / datetime 序列化。"""

    def default(self, obj):
        if isinstance(obj, UUID):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


async def write_audit(
    ctx: PipelineContext,
    effective_document_id,
    extraction_run_id,
    summary: dict,
) -> None:
    """向 audit_logs 写入一条 pipeline_completed 记录。"""
    serializable = json.loads(
        json.dumps(summary, cls=_UUIDEncoder)
    )
    async with async_session_maker() as session:
        record = AuditLog(
            user_id=None,  # v0.1 无真实用户
            action="pipeline_completed",
            target_type="extraction_run",
            target_id=str(extraction_run_id),
            before_value=None,
            after_value=serializable,
            trace_id=str(ctx.document_id),
        )
        session.add(record)
        await session.commit()
    logger.info("write_audit.done", extraction_run_id=str(extraction_run_id))
