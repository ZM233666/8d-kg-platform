"""s2 Splitter: 当前策略为整份文档只产出一个 chunk。"""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
import tiktoken

from app.pipeline.base import stage
from app.pipeline.context import PipelineContext
from app.schemas.entity import Chunk

logger = structlog.get_logger(__name__)

FULL_DOCUMENT_SECTION = ["full_document"]
FULL_DOCUMENT_ROLE = "unknown"


def _build_single_chunk(report_id: str, text: str) -> Chunk:
    """将整份文档构造成单个 chunk。"""
    encoder = tiktoken.get_encoding("cl100k_base")
    normalized_text = text.strip()
    now = datetime.now(UTC)
    return Chunk(
        chunk_id=f"{report_id}#full_document#0",
        report_id=report_id,
        section_path=FULL_DOCUMENT_SECTION,
        para_idx=0,
        chunk_role=FULL_DOCUMENT_ROLE,
        text=normalized_text,
        token_count=len(encoder.encode(normalized_text)),
        is_table=False,
        is_placeholder=False,
        has_referenced_image=False,
        created_at=now,
    )


@stage("s2_split")
async def run(ctx: PipelineContext) -> PipelineContext:
    """整份文档只保留一个 chunk, 避免同一 8D 报告被再次细切。"""
    if not ctx.raw_text:
        logger.warning("s2_split.skip_empty_text")
        return ctx

    raw_text = ctx.raw_text.strip()
    if not raw_text:
        logger.warning("s2_split.skip_empty_text")
        return ctx

    report_id = ctx.report_id_hint or "UNKNOWN"
    chunk = _build_single_chunk(report_id, raw_text)
    ctx.chunks = [chunk]

    logger.info(
        "s2_split.done",
        total=1,
        by_role={FULL_DOCUMENT_ROLE: 1},
        section_path=FULL_DOCUMENT_SECTION,
    )
    return ctx
