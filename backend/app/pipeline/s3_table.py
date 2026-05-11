"""s3 TableExtractor：把 ctx.raw_tables 按 table_patterns 归类，输出 ctx.parsed_tables。"""

from __future__ import annotations

import structlog

from app.lexicon import load_lexicon
from app.pipeline.base import stage
from app.pipeline.context import PipelineContext

logger = structlog.get_logger(__name__)


def _classify_table(headers: list[str], patterns: dict) -> str:
    """根据表头关键词匹配 table type。"""
    if not headers:
        return "unknown"

    header_set = {h.strip().upper() for h in headers}
    best_type: str | None = None
    best_score = -1

    for table_type, cfg in patterns.items():
        required: list[str] = cfg.get("required_headers", [])
        hit_count = 0
        for req in required:
            req_upper = req.upper()
            if any(req_upper in h.upper() for h in headers):
                hit_count += 1

        if hit_count == len(required):
            score = len(required)
            if score > best_score:
                best_score = score
                best_type = table_type
            elif score == best_score and best_type is not None:
                # 并列，取字典序最小
                if table_type < best_type:
                    best_type = table_type

    return best_type if best_type is not None else "unknown"


@stage("s3_table")
async def run(ctx: PipelineContext) -> PipelineContext:
    """把 ctx.raw_tables 归类到 ctx.parsed_tables。"""
    if not ctx.raw_tables:
        logger.info("s3_table.skip_no_tables")
        ctx.parsed_tables = {}
        return ctx

    lex = load_lexicon()
    patterns = lex.get("table_patterns", {})

    # 初始化所有类型（包含 unknown）
    all_types = list(patterns.keys()) + ["unknown"]
    buckets: dict[str, list[dict]] = {t: [] for t in all_types}

    for tbl in ctx.raw_tables:
        headers = tbl.get("headers", [])
        tbl_type = _classify_table(headers, patterns)
        buckets[tbl_type].append(tbl)

    # 过滤掉 unknown 桶（如果所有表都归类了，unknown 为空也可以）
    ctx.parsed_tables = {k: v for k, v in buckets.items() if v}

    for k, v in sorted(ctx.parsed_tables.items()):
        logger.info("s3_table.classified", type=k, count=len(v))

    return ctx
