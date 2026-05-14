"""s4 LLM Extractor (v0.2 KGtestV2)：单次调用，返回完整 ExtractionResult。

v0.2 简化：不再按章节路由分发，整篇 chunks 拼成一段 user_prompt，LLM（或 mock）一次性返回完整 ExtractionResult JSON。
真实 LLM 在 B4 接入，本批用 MockLLMClient 从 fixture 读取整段 ExtractionResult。
"""

from __future__ import annotations

import structlog

from app.llm import MockLLMClient
from app.llm import prompts as P
from app.pipeline.base import stage
from app.pipeline.context import PipelineContext
from app.schemas.extraction import ExtractionResult

logger = structlog.get_logger(__name__)


def _build_user_prompt(ctx: PipelineContext) -> str:
    """把所有 chunks 拼成单段 user_prompt（B4 LLM 时直接用，mock 阶段也无害）。"""
    report_id = ctx.report_id_hint or "UNKNOWN"
    chunk_lines: list[str] = []
    for c in ctx.chunks:
        section = "/".join(c.section_path) if c.section_path else ""
        chunk_lines.append(f"[chunk_id={c.chunk_id} section={section}]\n{c.text}")
    body = "\n\n".join(chunk_lines) if chunk_lines else "(无 chunks，请基于 report_id 生成占位结果)"
    template = getattr(P, "EXTRACTION_USER_TEMPLATE", None)
    if template:
        return template.format(report_id=report_id, text=body)
    # B3 兜底 prompt（B4 接 MiniMax 时替换为 prompts.py 里的完整版）
    return f"报告 ID: {report_id}\n\n【原文】\n{body}\n\n请输出完整 ExtractionResult JSON。"


@stage("s4_extract")
async def run(ctx: PipelineContext) -> PipelineContext:
    """单次 LLM 调用 → ExtractionResult。"""
    client = MockLLMClient()
    system_prompt = getattr(P, "EXTRACTION_SYSTEM", "你是 8D 报告抽取助手，输出严格符合 ExtractionResult JSON Schema。")
    user_prompt = _build_user_prompt(ctx)

    result, usage = await client.complete_json(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        response_model=ExtractionResult,
    )

    # 把 s2 切好的 chunks 塞回 ExtractionResult（LLM 不重复输出 chunks）
    result.chunks = ctx.chunks

    # 统计填入（s6_write._update_run_status 会读 llm_prompt_tokens / llm_completion_tokens）
    result.stats = {
        "llm_calls": 1,
        "llm_prompt_tokens": usage.prompt_tokens,
        "llm_completion_tokens": usage.completion_tokens,
        "llm_total_tokens": usage.total_tokens,
        "llm_model": usage.metadata.get("model", "mock-v0.1"),
    }

    ctx.extraction_result = result

    logger.info(
        "s4_extract.done",
        report=result.report.business_key if result.report else None,
        event_key=result.event.business_key if result.event else None,
        failure_modes=len(result.failure_modes),
        causes=len(result.causes),
        actions=len(result.actions),
        relationships=len(result.relationships),
        tokens=result.stats["llm_total_tokens"],
    )
    return ctx