"""s4 LLM Extractor (v0.2 KGtestV2)：单次调用，返回完整 ExtractionResult。

v0.2 简化：不再按章节路由分发，整篇 chunks 拼成一段 user_prompt，LLM（或 mock）一次性返回完整 ExtractionResult JSON。
真实 LLM 在 B4 接入，本批用 MockLLMClient 从 fixture 读取整段 ExtractionResult。
"""

from __future__ import annotations

import structlog

from app.core.config import settings
from app.llm import effective_llm_model, get_llm_client, prompts
from app.pipeline.base import stage
from app.pipeline.codex_skill_router import CodexSkillSelection, select_codex_skill
from app.pipeline.context import PipelineContext
from app.pipeline.relationship_builder import enrich_extraction_result
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
    template = getattr(prompts, "EXTRACTION_USER_TEMPLATE", None)
    if template:
        return template.format(report_id=report_id, text=body)
    # B3 兜底 prompt（B4 接 MiniMax 时替换为 prompts.py 里的完整版）
    return f"报告 ID: {report_id}\n\n【原文】\n{body}\n\n请输出完整 ExtractionResult JSON。"


def _build_system_prompt(skill_selection: CodexSkillSelection) -> str:
    """按 provider/route 组装 system prompt。"""
    if settings.llm_provider == "codex":
        return prompts.build_codex_system_prompt(
            skill_name=skill_selection.skill_name,
            skill_version=skill_selection.skill_version,
            route_name=skill_selection.route_name,
            execution_mode=skill_selection.execution_mode,
            prompt_modules=skill_selection.prompt_modules,
        )
    return getattr(prompts, "EXTRACTION_SYSTEM", "你是 8D 报告抽取助手，输出严格符合 ExtractionResult JSON Schema。")


@stage("s4_extract")
async def run(ctx: PipelineContext) -> PipelineContext:
    """单次 LLM 调用 → ExtractionResult。"""
    client = get_llm_client()
    skill_selection = select_codex_skill(ctx)
    system_prompt = _build_system_prompt(skill_selection)
    user_prompt = _build_user_prompt(ctx)

    result, usage = await client.complete_json(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        response_model=ExtractionResult,
        max_tokens=8192,
        temperature=0.1,
        request_context={
            "document_id": str(ctx.document_id),
            "extraction_run_id": str(ctx.extraction_run_id) if ctx.extraction_run_id else None,
            "report_id_hint": ctx.report_id_hint,
            "pipeline_version": ctx.pipeline_version,
            "schema_version": settings.pipeline.schema_version,
            "chunk_count": len(ctx.chunks),
            "route_name": skill_selection.route_name,
            "skill_name": skill_selection.skill_name,
            "skill_version": skill_selection.skill_version,
            "execution_mode": skill_selection.execution_mode,
            "prompt_modules": list(skill_selection.prompt_modules),
        },
    )

    # 同步 business_key、补全 relationships（LLM 常漏填或字段名不一致）
    result = enrich_extraction_result(result, report_id_hint=ctx.report_id_hint)

    # 把 s2 切好的 chunks 塞回 ExtractionResult（LLM 不重复输出 chunks）
    result.chunks = ctx.chunks

    # 统计填入（s6_write._update_run_status 会读 llm_prompt_tokens / llm_completion_tokens）
    result.stats = {
        "llm_calls": 1,
        "llm_prompt_tokens": usage.prompt_tokens,
        "llm_completion_tokens": usage.completion_tokens,
        "llm_total_tokens": usage.total_tokens,
        "llm_model": usage.model or usage.metadata.get("model") or effective_llm_model(),
        "executor_type": usage.metadata.get("executor_type", settings.llm_provider),
        "executor_provider": usage.metadata.get("provider", settings.llm_provider),
        "skill_name": usage.metadata.get("skill_name") or skill_selection.skill_name,
        "skill_version": usage.metadata.get("skill_version") or skill_selection.skill_version,
        "skill_route": usage.metadata.get("route_name") or skill_selection.route_name,
        "skill_modules": usage.metadata.get("prompt_modules") or list(skill_selection.prompt_modules),
        "fallback_provider": usage.metadata.get("fallback_provider"),
        "primary_provider": usage.metadata.get("primary_provider"),
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
        executor_type=result.stats.get("executor_type"),
        skill_name=result.stats.get("skill_name"),
        skill_modules=result.stats.get("skill_modules"),
    )
    return ctx
