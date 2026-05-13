"""s4 LLM Extractor：按 chapter_routing 把 chunks 分发到 5 个子模块。

输入：ctx.chunks（带 chapter_path）
输出：ctx.extraction_result = ExtractionResult(...)

v0.1 用 MockLLMClient，路由后聚合到 ExtractionResult。
真实 chunks 来自 s2_split，本批 mock 路由会容忍空 chunks（也能产出 mock 结果）。
"""

from __future__ import annotations

from datetime import datetime, timezone

import structlog

from app.lexicon import load_lexicon
from app.llm import MockLLMClient
from app.llm import prompts as P
from app.pipeline.base import stage
from app.pipeline.context import PipelineContext
from app.schemas.entity import (
    ActionEvent,
    ClosureEvent,
    DefectOccurrence,
    EightDReport,
    RiskAssessment,
    VerificationEvent,
)
from app.schemas.extraction import ExtractionResult, RootCauseAnalysisOutput

logger = structlog.get_logger(__name__)


def _classify_chunks(chunks, lex) -> dict[str, list]:
    """按 lexicon.chapter_routing 把 chunks 分到 7 类。"""
    routing = lex.get("chapter_routing", {})
    buckets: dict[str, list] = {k: [] for k in routing}
    for c in chunks:
        sect = " ".join(c.section_path) if hasattr(c, "section_path") else ""
        for route_name, keywords in routing.items():
            if any(kw in sect for kw in keywords):
                buckets[route_name].append(c)
                break
    return buckets


def _join_text(chunks) -> str:
    return "\n\n".join(c.text for c in chunks) if chunks else ""


def _chapter_path_label(chunks) -> str:
    if not chunks:
        return ""
    return " > ".join(chunks[0].section_path) if hasattr(chunks[0], "section_path") else ""


@stage("s4_extract")
async def run(ctx: PipelineContext) -> PipelineContext:
    lex = load_lexicon()
    buckets = _classify_chunks(ctx.chunks, lex)
    report_id = ctx.report_id_hint or "MOCK-REPORT"
    now = datetime.now(timezone.utc)

    total_usage_tokens = 0
    total_prompt_tokens = 0
    total_completion_tokens = 0

    # 1. Defect（mock 无视 chunks 是否为空，固定返回样本）
    client_defect = MockLLMClient()
    defects, u = await client_defect.complete_json(
        system_prompt=P.DEFECT_SYSTEM,
        user_prompt=P.DEFECT_USER_TEMPLATE.format(
            report_id=report_id,
            chapter_path=_chapter_path_label(buckets.get("defect", [])),
            text=_join_text(buckets.get("defect", [])),
        ),
        response_model=list[DefectOccurrence],
    )
    total_usage_tokens += u.total_tokens
    total_prompt_tokens += u.prompt_tokens
    total_completion_tokens += u.completion_tokens

    # 2. RCA
    client_rca = MockLLMClient()
    rca_out, u = await client_rca.complete_json(
        system_prompt=P.RCA_SYSTEM,
        user_prompt=P.RCA_USER_TEMPLATE.format(
            report_id=report_id,
            chapter_path=_chapter_path_label(buckets.get("root_cause", [])),
            text=_join_text(buckets.get("root_cause", [])),
        ),
        response_model=RootCauseAnalysisOutput,
    )
    total_usage_tokens += u.total_tokens
    total_prompt_tokens += u.prompt_tokens
    total_completion_tokens += u.completion_tokens

    # 3. Containment / 4. Corrective / 5. Preventive Action
    actions: list[ActionEvent] = []
    for route, hint in [
        ("containment", "containment"),
        ("corrective_action", "corrective"),
        ("preventive_action", "preventive"),
    ]:
        client_a = MockLLMClient(action_type_hint=hint)
        acts, u = await client_a.complete_json(
            system_prompt=P.ACTION_SYSTEM,
            user_prompt=P.ACTION_USER_TEMPLATE.format(
                report_id=report_id,
                chapter_path=_chapter_path_label(buckets.get(route, [])),
                text=_join_text(buckets.get(route, [])),
                action_type=hint,
            ),
            response_model=list[ActionEvent],
        )
        actions.extend(acts)
        total_usage_tokens += u.total_tokens
        total_prompt_tokens += u.prompt_tokens
        total_completion_tokens += u.completion_tokens

    # 6. Verification
    client_v = MockLLMClient()
    verifications, u = await client_v.complete_json(
        system_prompt=P.VERIFICATION_SYSTEM,
        user_prompt=P.VERIFICATION_USER_TEMPLATE.format(
            report_id=report_id,
            chapter_path=_chapter_path_label(buckets.get("verification", [])),
            text=_join_text(buckets.get("verification", [])),
        ),
        response_model=list[VerificationEvent],
    )
    total_usage_tokens += u.total_tokens
    total_prompt_tokens += u.prompt_tokens
    total_completion_tokens += u.completion_tokens

    # 7. Closure（单条，不是 list）
    client_c = MockLLMClient()
    closure, u = await client_c.complete_json(
        system_prompt=P.CLOSURE_SYSTEM,
        user_prompt=P.CLOSURE_USER_TEMPLATE.format(
            report_id=report_id,
            chapter_path=_chapter_path_label(buckets.get("closure", [])),
            text=_join_text(buckets.get("closure", [])),
        ),
        response_model=ClosureEvent,
    )
    total_usage_tokens += u.total_tokens
    total_prompt_tokens += u.prompt_tokens
    total_completion_tokens += u.completion_tokens

    # 8. RiskAssessment（mock 固定返回样本）
    client_r = MockLLMClient()
    risks, u = await client_r.complete_json(
        system_prompt=P.RCA_SYSTEM,
        user_prompt="risk",
        response_model=list[RiskAssessment],
    )
    total_usage_tokens += u.total_tokens
    total_prompt_tokens += u.prompt_tokens
    total_completion_tokens += u.completion_tokens

    # 9. 构造最小 EightDReport（mock，从 hint 拿 report_id）
    report = EightDReport(
        business_key=report_id,
        report_id=report_id,
        title="Mock 8D 报告",
        closure_status="root_cause_unidentified",
        source_doc_id=str(ctx.document_id),
        confidence=0.85,
        extraction_version=ctx.pipeline_version,
        owner_id="system",
        created_at=now,
        updated_at=now,
    )

    # 10. 聚合 ExtractionResult
    ctx.extraction_result = ExtractionResult(
        doc_id=ctx.document_id,
        report_id=report_id,
        extraction_version=ctx.pipeline_version,
        schema_version="v0.1.0",
        report=report,
        defect_occurrences=defects,
        inspection_events=rca_out.inspection_events,
        experiments=rca_out.experiments,
        actions=actions,
        verifications=verifications,
        closure=closure,
        measurements=rca_out.measurements,
        findings=rca_out.findings,
        root_causes=rca_out.root_causes,
        risk_assessments=risks,
        chunks=ctx.chunks,
        stats={
            "llm_total_tokens": total_usage_tokens,
            "llm_prompt_tokens": total_prompt_tokens,
            "llm_completion_tokens": total_completion_tokens,
            "llm_calls": 8,
        },
    )

    logger.info(
        "s4_extract.done",
        defects=len(defects),
        rcas=len(rca_out.root_causes),
        actions=len(actions),
        verifications=len(verifications),
        risks=len(risks),
        llm_tokens=total_usage_tokens,
    )
    return ctx