"""s6 Writer：把 ExtractionResult + Chunks 持久化到 PG 和 Neo4j。

事务策略（PRD 决策 2A）：
- PG 一个事务：写 documents.status 更新、chunks 批量插入、extraction_runs 完成标记
- Neo4j 一个 session：MERGE 所有节点 + 关系，幂等
- 两个独立，崩一个另一个保留；靠 MERGE + sha256 保证重跑安全
"""

from __future__ import annotations

from datetime import datetime, timezone

import structlog
from sqlalchemy import update

from app.db.postgres import async_session_maker
from app.models import ExtractionRun
from app.pipeline.base import stage
from app.pipeline.context import PipelineContext
from app.pipeline.writers import write_audit, write_neo4j, write_pg

logger = structlog.get_logger(__name__)


async def _update_run_status(
    run_id,
    status: str,
    stats: dict | None = None,
    error: str | None = None,
) -> None:
    """更新 extraction_runs 的状态（在新 session 中）。"""
    async with async_session_maker() as session:
        now = datetime.now(timezone.utc)
        upd: dict = {"status": status, "finished_at": now}
        if stats:
            upd["stage_metrics"] = stats
            if "llm_prompt_tokens" in stats:
                upd["token_input"] = stats["llm_prompt_tokens"]
            if "llm_completion_tokens" in stats:
                upd["token_output"] = stats["llm_completion_tokens"]
        if error is not None:
            upd["error_detail"] = {"error": error}
        stmt = update(ExtractionRun).where(ExtractionRun.id == run_id).values(**upd)
        await session.execute(stmt)
        await session.commit()


@stage("s6_write")
async def run(ctx: PipelineContext) -> PipelineContext:
    if ctx.extraction_result is None:
        raise ValueError("s6_write requires ctx.extraction_result, got None")

    er = ctx.extraction_result

    # 1. 写 PG（documents + chunks + extraction_run）
    pg_result = await write_pg(ctx)
    ctx.extraction_run_id = pg_result["extraction_run_id"]
    effective_document_id = pg_result["document_id"]

    # 2. 写 Neo4j；失败则更新 extraction_run 为 failed 后向上抛
    try:
        neo4j_result = await write_neo4j(
            ctx,
            effective_document_id=effective_document_id,
            extraction_run_id=ctx.extraction_run_id,
        )
    except Exception as e:
        await _update_run_status(ctx.extraction_run_id, "failed", error=str(e))
        raise

    # 3. 更新 extraction_run 为 succeeded
    await _update_run_status(
        ctx.extraction_run_id,
        "succeeded",
        stats=er.stats,
    )

    # 4. 写 audit_log
    summary = {
        "pg": pg_result,
        "neo4j": neo4j_result,
        "stats": er.stats,
        "report_id": er.report.business_key if er.report else None,
    }
    await write_audit(ctx, effective_document_id, ctx.extraction_run_id, summary)

    logger.info("s6_write.done", **summary)
    return ctx
