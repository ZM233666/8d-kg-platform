"""Codex 抽取 skill 路由器。

当前阶段先提供“整份报告单次抽取”的默认路由，后续再与用户共同细化为
章节级 / chunk_role 级的 skill 选择策略。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings
from app.pipeline.context import PipelineContext

D2_SECTION_KEYWORDS: tuple[str, ...] = (
    "问题描述",
    "故障描述",
    "故障现象",
    "客诉",
    "投诉",
    "异常",
    "事件",
    "试验",
    "问题定义",
    "故障信息",
)
D2_TEXT_KEYWORDS: tuple[str, ...] = (
    "发生",
    "出现",
    "故障",
    "异常",
    "客诉",
    "投诉",
    "报警",
    "试验",
    "上报",
    "现象",
)
D4_SECTION_KEYWORDS: tuple[str, ...] = (
    "根因",
    "原因分析",
    "原因验证",
    "5WHY",
    "鱼骨",
    "失效分析",
)
D4_TEXT_KEYWORDS: tuple[str, ...] = (
    "根因",
    "原因",
    "导致",
    "由于",
    "验证",
    "5WHY",
)
D5_SECTION_KEYWORDS: tuple[str, ...] = (
    "措施",
    "纠正",
    "预防",
    "验证",
    "遏制",
    "防再发",
)
D5_TEXT_KEYWORDS: tuple[str, ...] = (
    "措施",
    "整改",
    "更换",
    "隔离",
    "返工",
    "培训",
    "检验",
    "预防",
    "验证",
)


class CodexSkillSelection(BaseModel):
    """一次抽取调用对应的 skill 选择结果。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    route_name: str = Field(..., description="路由名，便于后续扩展多种抽取路径")
    skill_name: str = Field(..., description="Codex skill 名称")
    skill_version: str = Field(..., description="Codex skill 版本")
    execution_mode: str = Field(..., description="执行模式，如 single_pass_document")
    prompt_modules: tuple[str, ...] = Field(
        default_factory=tuple,
        description="本次调用附带的 skill 模块列表",
    )


def _contains_keyword(value: str, keywords: tuple[str, ...]) -> bool:
    upper_value = value.upper()
    return any(keyword in value or keyword.upper() in upper_value for keyword in keywords)


def _has_section_signal(
    *,
    section_path: list[str],
    exact_steps: frozenset[str],
    keywords: tuple[str, ...],
) -> bool:
    parts = [part.strip() for part in section_path if part and part.strip()]
    return any(part.upper() in exact_steps or _contains_keyword(part, keywords) for part in parts)


def _has_text_fallback(text: str, keywords: tuple[str, ...]) -> bool:
    return bool(text.strip()) and _contains_keyword(text, keywords)


def _has_full_report_text_signal(
    *,
    section_path: list[str],
    chunk_role: str | None,
    text: str,
    keywords: tuple[str, ...],
) -> bool:
    return (
        section_path == ["全文"] or not section_path or chunk_role in {"unknown", "evidence", "conclusion"}
    ) and _has_text_fallback(text, keywords)


def select_codex_skill(ctx: PipelineContext) -> CodexSkillSelection:
    """返回当前上下文对应的 Codex skill。

    v0.3 骨架阶段先走整篇单次抽取；真正的章节级 skill 细化将在后续与用户共同完成。
    """

    modules: list[str] = [
        "8d-report-extraction-core",
        "8d-actor-entity-typing",
        "8d-temporal-normalization",
        "8d-relationship-normalization",
    ]

    has_d2_signal = any(
        _has_section_signal(
            section_path=c.section_path,
            exact_steps=frozenset({"D2"}),
            keywords=D2_SECTION_KEYWORDS,
        )
        or (
            _has_full_report_text_signal(
                section_path=c.section_path,
                chunk_role=c.chunk_role,
                text=c.text,
                keywords=D2_TEXT_KEYWORDS,
            )
        )
        for c in ctx.chunks
    )
    if has_d2_signal:
        modules.append("8d-d2-event-extraction")

    has_d4_signal = any(
        c.chunk_role == "hypothesis"
        or _has_section_signal(
            section_path=c.section_path,
            exact_steps=frozenset({"D4"}),
            keywords=D4_SECTION_KEYWORDS,
        )
        or (
            _has_full_report_text_signal(
                section_path=c.section_path,
                chunk_role=c.chunk_role,
                text=c.text,
                keywords=D4_TEXT_KEYWORDS,
            )
        )
        for c in ctx.chunks
    )
    if has_d4_signal:
        modules.append("8d-d4-root-cause-extraction")

    has_d5_signal = any(
        c.chunk_role == "action"
        or _has_section_signal(
            section_path=c.section_path,
            exact_steps=frozenset({"D3", "D5", "D6", "D7"}),
            keywords=D5_SECTION_KEYWORDS,
        )
        or (
            _has_full_report_text_signal(
                section_path=c.section_path,
                chunk_role=c.chunk_role,
                text=c.text,
                keywords=D5_TEXT_KEYWORDS,
            )
        )
        for c in ctx.chunks
    )
    if has_d5_signal:
        modules.append("8d-d5-action-extraction")

    return CodexSkillSelection(
        route_name="full_report_single_pass",
        skill_name=settings.codex_skill_name,
        skill_version=settings.codex_skill_version,
        execution_mode="single_pass_document",
        prompt_modules=tuple(modules),
    )
