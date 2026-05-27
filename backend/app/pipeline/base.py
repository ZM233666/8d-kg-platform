"""Stage 抽象基类 + 装饰器 + run_pipeline 编排。"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from functools import wraps
from typing import Protocol

import structlog

from app.pipeline.context import PipelineContext, StageMetric

logger = structlog.get_logger(__name__)


class Stage(Protocol):
    """所有 stage 必须实现的协议（duck typing，不继承）。"""

    name: str

    async def __call__(self, ctx: PipelineContext) -> PipelineContext: ...


def stage(name: str) -> Callable[[Callable[..., Awaitable[PipelineContext]]], Stage]:
    """装饰器：把 async 函数包成带指标采集和异常处理的 Stage。

    用法：
        @stage("s1_parse")
        async def run(ctx: PipelineContext) -> PipelineContext:
            ...
    """

    def decorator(func: Callable[..., Awaitable[PipelineContext]]) -> Stage:
        @wraps(func)
        async def wrapper(ctx: PipelineContext) -> PipelineContext:
            started = datetime.now(UTC)
            t0 = time.perf_counter()
            metric = StageMetric(stage_name=name, started_at=started)
            try:
                logger.info("stage.start", stage=name, document_id=str(ctx.document_id))
                ctx = await func(ctx)
                metric.ok = True
                metric.output_summary = _summarize(ctx, name)
            except Exception as e:
                metric.ok = False
                metric.error = f"{type(e).__name__}: {e}"
                ctx.add_error(name, metric.error)
                logger.exception("stage.fail", stage=name, error=metric.error)
                raise
            finally:
                metric.finished_at = datetime.now(UTC)
                metric.duration_ms = (time.perf_counter() - t0) * 1000
                ctx.add_metric(metric)
                if metric.ok:
                    logger.info(
                        "stage.ok",
                        stage=name,
                        duration_ms=round(metric.duration_ms, 2),
                    )
            return ctx

        # type: ignore[attr-defined]
        wrapper.name = name
        return wrapper  # type: ignore[return-value]

    return decorator


def _summarize(ctx: PipelineContext, stage_name: str) -> dict:
    """从 ctx 提取该 stage 的产出摘要。"""
    return {
        "raw_text_len": len(ctx.raw_text),
        "raw_tables": len(ctx.raw_tables),
        "chunks": len(ctx.chunks),
        "parsed_table_types": len(ctx.parsed_tables),
        "has_extraction_result": ctx.extraction_result is not None,
    }


async def run_pipeline(
    ctx: PipelineContext,
    stages: list[Stage],
    *,
    fail_fast: bool = True,
) -> PipelineContext:
    """依序执行 stages。fail_fast=True 时任一失败即抛出。"""
    for stg in stages:
        try:
            ctx = await stg(ctx)
        except Exception:
            if fail_fast:
                raise
            logger.warning("pipeline.stage_failed_continue", stage=stg.name)
    return ctx
