"""s6 Writer：把 ExtractionResult + Chunks 持久化到 PG 和 Neo4j。

事务策略（PRD 决策 2A）：
- PG 一个事务：写 documents.status 更新、chunks 批量插入、extraction_runs 完成标记
- Neo4j 一个 session：MERGE 所有节点 + 关系，幂等
- 两个独立，崩一个另一个保留；靠 MERGE + sha256 保证重跑安全
"""

from __future__ import annotations

import structlog

from app.pipeline.base import stage
from app.pipeline.context import PipelineContext

logger = structlog.get_logger(__name__)


@stage("s6_write")
async def run(ctx: PipelineContext) -> PipelineContext:
    if ctx.extraction_result is None:
        raise ValueError("s6_write requires ctx.extraction_result, got None")

    # TODO: 批 5D 补 PG 写入（chunks 批量插入 + status 更新 + extraction_run 完成）
    # TODO: 批 5D 补 Neo4j 写入（遍历 ExtractionResult 各类，
    #        调用 Neo4jClient.merge_node / merge_relationship）
    # 当前框架仅打 log 占位，便于跑通端到端骨架。

    er = ctx.extraction_result
    logger.info(
        "s6_write.placeholder",
        document_id=str(ctx.document_id),
        report_id=er.report_id,
        chunks=len(er.chunks),
        defects=len(er.defect_occurrences),
        root_causes=len(er.root_causes),
        actions=len(er.actions),
    )
    return ctx
