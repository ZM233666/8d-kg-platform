"""PG Writer: 将 ExtractionResult + Chunks 写入 PostgreSQL。"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import structlog
from sqlalchemy import delete, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.postgres import async_session_maker
from app.llm import effective_llm_model
from app.models import Chunk, Document, ExtractionRun
from app.pipeline.context import PipelineContext

logger = structlog.get_logger(__name__)


def _compute_sha256(minio_key: str) -> str:
    """对 local:// 文件计算 sha256；非本地路径返回占位符。"""
    if minio_key.startswith("local://"):
        path = Path(minio_key[8:])
        if path.exists():
            return hashlib.sha256(path.read_bytes()).hexdigest()
    return None  # 非本地或不存在，sha256 由调用方兜底


async def write_pg(ctx: PipelineContext) -> dict:
    """将文档元数据、chunks 和 extraction_run 记录写入 PG。

    Returns
        dict: {"document_id": UUID, "extraction_run_id": UUID, "chunks_written": int}
    """
    er = ctx.extraction_result
    now = datetime.now(UTC)

    # --- 解析 minio_key，确定文件名 / 路径 ---
    raw_key = ctx.minio_key
    if raw_key.startswith("local://"):
        local_path = Path(raw_key[8:])
        file_name = local_path.name
        file_size = local_path.stat().st_size if local_path.exists() else 0
        sha256 = _compute_sha256(raw_key) or f"mock-sha-{ctx.document_id}"
        mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    else:
        # minio:// URL: use a stable hash of the object key for deduplication
        # (computing real SHA256 would require re-downloading from MinIO)
        file_name = raw_key.split("/")[-1]
        file_size = 0
        sha256 = hashlib.sha256(raw_key.encode()).hexdigest()
        mime_type = "application/octet-stream"

    # --- UPSERT documents（按 sha256 去重）---
    async with async_session_maker() as session:
        doc_stmt = (
            pg_insert(Document)
            .values(
                file_name=file_name,
                file_size=file_size,
                mime_type=mime_type,
                sha256=sha256,
                minio_key=raw_key,
                upload_user_id=UUID("00000000-0000-0000-0000-000000000000"),
                status="extracted",
            )
            .returning(Document.id)
        )
        doc_stmt = doc_stmt.on_conflict_do_update(
            index_elements=["sha256"],
            set_={
                "status": "extracted",
                "file_size": file_size,
                "updated_at": now,
            },
        )
        result = await session.execute(doc_stmt)
        effective_document_id: UUID = result.scalar_one()

        # --- extraction_runs：根据 ctx.extraction_run_id 决定 INSERT 还是 UPDATE ---
        if ctx.extraction_run_id:
            # Celery 异步路径：endpoint 已 INSERT(status='pending')，这里只 UPDATE 为 running
            update_stmt = (
                update(ExtractionRun)
                .where(ExtractionRun.id == ctx.extraction_run_id)
                .values(
                    status="running",
                    started_at=now,
                    llm_model=effective_llm_model(),
                )
            )
            await session.execute(update_stmt)
            extraction_run_id: UUID = ctx.extraction_run_id
        else:
            # 同步路径（向后兼容）：直接 INSERT
            run_stmt = (
                pg_insert(ExtractionRun)
                .values(
                    document_id=effective_document_id,
                    pipeline_version=ctx.pipeline_version,
                    llm_model=effective_llm_model(),
                    started_at=now,
                    status="running",
                )
                .returning(ExtractionRun.id)
            )
            run_result = await session.execute(run_stmt)
            extraction_run_id = run_result.scalar_one()

        # --- BATCH INSERT chunks（按 chunk_business_key 幂等）---
        chunk_rows = []
        for c in er.chunks:
            # chunk_business_key 对应 schema Chunk.chunk_id
            chunk_business_key = c.chunk_id
            chunk_rows.append(
                {
                    "document_id": effective_document_id,
                    "chunk_index": c.para_idx,
                    "chunk_business_key": chunk_business_key,
                    "chapter_path": c.section_path or [],
                    "text": c.text,
                    "token_count": c.token_count,
                    "chunk_role": c.chunk_role or None,
                    "is_table": c.is_table,
                    "is_placeholder": c.is_placeholder,
                    "table_type": c.table_type or None,
                    "has_referenced_image": getattr(c, "has_referenced_image", False),
                }
            )

        if chunk_rows:
            # 同一源文件会按 sha256 复用 document_id；重抽时先刷新该文档的 chunk 镜像。
            await session.execute(
                delete(Chunk).where(Chunk.document_id == effective_document_id)
            )
            chunks_stmt = pg_insert(Chunk).values(chunk_rows)
            chunks_stmt = chunks_stmt.on_conflict_do_nothing()
            await session.execute(chunks_stmt)

        await session.commit()
        chunks_written = len(chunk_rows)

    logger.info(
        "write_pg.done",
        document_id=str(effective_document_id),
        extraction_run_id=str(extraction_run_id),
        chunks_written=chunks_written,
    )
    return {
        "document_id": effective_document_id,
        "extraction_run_id": extraction_run_id,
        "chunks_written": chunks_written,
    }
