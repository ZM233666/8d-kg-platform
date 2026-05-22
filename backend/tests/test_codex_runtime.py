"""Codex 抽取运行时骨架测试。"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from app.core.config import settings
from app.llm import CodexClient, MinimaxClient, build_llm_client, get_llm_client, prompts
from app.llm.base import LLMError, LLMUsage
from app.llm.fallback_client import FallbackLLMClient
from app.pipeline import s4_extract
from app.pipeline.codex_skill_router import select_codex_skill
from app.pipeline.context import PipelineContext
from app.schemas.entity import Chunk, EightDReport
from app.schemas.extraction import ExtractionResult


def _build_ctx() -> PipelineContext:
    return PipelineContext(
        document_id=uuid4(),
        minio_key="documents/fs-001.docx",
        report_id_hint="FS-001",
        chunks=[
            Chunk(
                chunk_id="FS-001#D4#1",
                report_id="FS-001",
                section_path=["D4"],
                para_idx=1,
                chunk_role="hypothesis",
                text="弹簧在根部出现疲劳裂纹，怀疑热处理异常。",
                token_count=18,
            )
        ],
    )


def _build_d2_ctx() -> PipelineContext:
    return PipelineContext(
        document_id=uuid4(),
        minio_key="documents/fs-000.docx",
        report_id_hint="FS-000",
        chunks=[
            Chunk(
                chunk_id="FS-000#D2#1",
                report_id="FS-000",
                section_path=["D2", "问题描述"],
                para_idx=1,
                chunk_role="evidence",
                text="客户反馈 EP2002 阀在出厂测试时密封面渗油，现象持续出现。",
                token_count=26,
            )
        ],
    )


def _build_action_ctx() -> PipelineContext:
    return PipelineContext(
        document_id=uuid4(),
        minio_key="documents/fs-002.docx",
        report_id_hint="FS-002",
        chunks=[
            Chunk(
                chunk_id="FS-002#D5#1",
                report_id="FS-002",
                section_path=["D5"],
                para_idx=1,
                chunk_role="action",
                text="更换为 Viton 材质 O 型圈，并于 2026-04-20 前完成。",
                token_count=20,
            )
        ],
    )


def _build_full_report_ctx() -> PipelineContext:
    return PipelineContext(
        document_id=uuid4(),
        minio_key="documents/fs-003.docx",
        report_id_hint="FS-003",
        chunks=[
            Chunk(
                chunk_id="FS-003#D2#1",
                report_id="FS-003",
                section_path=["D2", "问题描述"],
                para_idx=1,
                chunk_role="evidence",
                text="客户投诉 EP2002 阀在出厂测试时密封面渗油。",
                token_count=18,
            ),
            Chunk(
                chunk_id="FS-003#D4#1",
                report_id="FS-003",
                section_path=["D4", "根因分析"],
                para_idx=1,
                chunk_role="hypothesis",
                text="分析认为 O 型圈硬度低于图纸要求，导致密封失效。",
                token_count=19,
            ),
            Chunk(
                chunk_id="FS-003#D5#1",
                report_id="FS-003",
                section_path=["D5", "纠正措施"],
                para_idx=1,
                chunk_role="action",
                text="更换为 Viton 材质 O 型圈，并对同批次产品加严筛查。",
                token_count=22,
            ),
        ],
    )


def _build_unknown_full_report_ctx() -> PipelineContext:
    return PipelineContext(
        document_id=uuid4(),
        minio_key="documents/fs-004.docx",
        report_id_hint="FS-004",
        chunks=[
            Chunk(
                chunk_id="FS-004#全文#0",
                report_id="FS-004",
                section_path=["全文"],
                para_idx=0,
                chunk_role="unknown",
                text=(
                    "2022/8/19 车辆静调首次上电自检失败，制动系统报二级调节器压力超差故障。"
                    "分析认为活塞销存在气孔导致变形。"
                    "后续更换故障阀并对库存件100%外观检。"
                ),
                token_count=42,
            )
        ],
    )


def _build_full_document_ctx() -> PipelineContext:
    return PipelineContext(
        document_id=uuid4(),
        minio_key="documents/fs-005.docx",
        report_id_hint="FS-005",
        chunks=[
            Chunk(
                chunk_id="FS-005#full_document#0",
                report_id="FS-005",
                section_path=["full_document"],
                para_idx=0,
                chunk_role="unknown",
                text=(
                    "D2 问题描述：2022/8/19 车辆静调首次上电自检失败，制动系统报二级调节器压力超差故障。"
                    "D4 根因分析：分析认为活塞销存在气孔导致变形。"
                    "D5 纠正措施：更换故障阀并对库存件100%外观检。"
                ),
                token_count=48,
            )
        ],
    )


def test_select_codex_skill_returns_default_document_route() -> None:
    selection = select_codex_skill(_build_ctx())

    assert selection.route_name == "full_report_single_pass"
    assert selection.execution_mode == "single_pass_document"
    assert selection.skill_name == settings.codex_skill_name
    assert selection.prompt_modules == (
        "8d-report-extraction-core",
        "8d-actor-entity-typing",
        "8d-temporal-normalization",
        "8d-relationship-normalization",
        "8d-d4-root-cause-extraction",
    )


def test_build_codex_system_prompt_includes_selected_modules() -> None:
    prompt = prompts.build_codex_system_prompt(
        skill_name="8d-report-extraction-core",
        skill_version="draft-1",
        route_name="full_report_single_pass",
        execution_mode="single_pass_document",
        prompt_modules=(
            "8d-report-extraction-core",
            "8d-actor-entity-typing",
            "8d-temporal-normalization",
            "8d-relationship-normalization",
            "8d-d4-root-cause-extraction",
        ),
    )

    assert "Skill Module: 8d-report-extraction-core" in prompt
    assert "Skill Module: 8d-actor-entity-typing" in prompt
    assert "Skill Module: 8d-temporal-normalization" in prompt
    assert "Skill Module: 8d-relationship-normalization" in prompt
    assert "Skill Module: 8d-d4-root-cause-extraction" in prompt
    assert "最终只输出当前 runtime 支持的 ExtractionResult JSON" in prompt


def test_build_llm_client_supports_minimax_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "minimax_api_key", "test-minimax-key")
    monkeypatch.setattr(settings, "minimax_base_url", "https://api.minimax.chat/v1")
    monkeypatch.setattr(settings, "minimax_model", "MiniMax-M2.7")
    monkeypatch.setattr(settings, "minimax_timeout_seconds", 45)
    monkeypatch.setattr(settings, "minimax_max_retries", 2)

    client = build_llm_client("minimax")

    assert isinstance(client, MinimaxClient)
    assert client.base_url == "https://api.minimax.chat/v1"
    assert client.model == "MiniMax-M2.7"


def test_get_llm_client_wraps_codex_with_minimax_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "llm_provider", "codex")
    monkeypatch.setattr(settings, "llm_fallback_provider", "minimax")
    monkeypatch.setattr(settings, "llm_primary_soft_timeout_seconds", 30)
    monkeypatch.setattr(settings, "minimax_api_key", "test-minimax-key")
    monkeypatch.setattr(settings, "minimax_base_url", "https://api.minimax.chat/v1")
    monkeypatch.setattr(settings, "minimax_model", "MiniMax-M2.7")

    client = get_llm_client()

    assert isinstance(client, FallbackLLMClient)
    assert isinstance(client.primary, CodexClient)
    assert isinstance(client.fallback, MinimaxClient)
    assert client.primary_provider == "codex"
    assert client.fallback_provider == "minimax"
    assert client.primary_timeout_seconds == 30


def test_select_codex_skill_adds_d2_module_for_event_chunks() -> None:
    selection = select_codex_skill(_build_d2_ctx())

    assert selection.route_name == "full_report_single_pass"
    assert selection.execution_mode == "single_pass_document"
    assert selection.prompt_modules == (
        "8d-report-extraction-core",
        "8d-actor-entity-typing",
        "8d-temporal-normalization",
        "8d-relationship-normalization",
        "8d-d2-event-extraction",
    )


def test_build_codex_system_prompt_can_include_d2_module() -> None:
    prompt = prompts.build_codex_system_prompt(
        skill_name="8d-report-extraction-core",
        skill_version="draft-1",
        route_name="full_report_single_pass",
        execution_mode="single_pass_document",
        prompt_modules=(
            "8d-report-extraction-core",
            "8d-actor-entity-typing",
            "8d-temporal-normalization",
            "8d-relationship-normalization",
            "8d-d2-event-extraction",
        ),
    )

    assert "Skill Module: 8d-relationship-normalization" in prompt
    assert "Skill Module: 8d-d2-event-extraction" in prompt
    assert "当前 runtime 下 D2 可直接落的结构" in prompt


def test_select_codex_skill_adds_d5_module_for_action_chunks() -> None:
    selection = select_codex_skill(_build_action_ctx())

    assert selection.route_name == "full_report_single_pass"
    assert selection.execution_mode == "single_pass_document"
    assert selection.prompt_modules == (
        "8d-report-extraction-core",
        "8d-actor-entity-typing",
        "8d-temporal-normalization",
        "8d-relationship-normalization",
        "8d-d5-action-extraction",
    )


def test_select_codex_skill_adds_d2_d4_d5_modules_for_mixed_report() -> None:
    selection = select_codex_skill(_build_full_report_ctx())

    assert selection.route_name == "full_report_single_pass"
    assert selection.execution_mode == "single_pass_document"
    assert selection.prompt_modules == (
        "8d-report-extraction-core",
        "8d-actor-entity-typing",
        "8d-temporal-normalization",
        "8d-relationship-normalization",
        "8d-d2-event-extraction",
        "8d-d4-root-cause-extraction",
        "8d-d5-action-extraction",
    )


def test_select_codex_skill_adds_d2_d4_d5_modules_for_unknown_full_report_chunk() -> None:
    selection = select_codex_skill(_build_unknown_full_report_ctx())

    assert selection.prompt_modules == (
        "8d-report-extraction-core",
        "8d-actor-entity-typing",
        "8d-temporal-normalization",
        "8d-relationship-normalization",
        "8d-d2-event-extraction",
        "8d-d4-root-cause-extraction",
        "8d-d5-action-extraction",
    )


def test_select_codex_skill_adds_d2_d4_d5_modules_for_full_document_chunk() -> None:
    selection = select_codex_skill(_build_full_document_ctx())

    assert selection.prompt_modules == (
        "8d-report-extraction-core",
        "8d-actor-entity-typing",
        "8d-temporal-normalization",
        "8d-relationship-normalization",
        "8d-d2-event-extraction",
        "8d-d4-root-cause-extraction",
        "8d-d5-action-extraction",
    )


def test_build_codex_system_prompt_can_include_d5_module() -> None:
    prompt = prompts.build_codex_system_prompt(
        skill_name="8d-report-extraction-core",
        skill_version="draft-1",
        route_name="full_report_single_pass",
        execution_mode="single_pass_document",
        prompt_modules=(
            "8d-report-extraction-core",
            "8d-actor-entity-typing",
            "8d-temporal-normalization",
            "8d-relationship-normalization",
            "8d-d5-action-extraction",
        ),
    )

    assert "Skill Module: 8d-relationship-normalization" in prompt
    assert "Skill Module: 8d-d5-action-extraction" in prompt
    assert "当前 runtime 下 D5 可直接落的结构" in prompt


@pytest.mark.asyncio
async def test_codex_client_validates_response_and_carries_skill_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = CodexClient(
        base_url="http://127.0.0.1:8787",
        extract_path="/extract",
        executor_label="codex-local",
    )

    async def fake_post(url: str, payload: dict) -> dict:
        assert url == "http://127.0.0.1:8787/extract"
        assert payload["request_context"]["skill_name"] == "8d-report-extraction-core"
        assert payload["request_context"]["prompt_modules"] == [
            "8d-report-extraction-core",
            "8d-actor-entity-typing",
            "8d-temporal-normalization",
            "8d-relationship-normalization",
            "8d-d4-root-cause-extraction",
        ]
        return {
            "data": {
                "report": {
                    "business_key": "FS-001",
                    "report_no": "FS-001",
                    "confidence": "0.91",
                    "sensitivity": "public",
                }
            },
            "usage": {
                "prompt_tokens": 120,
                "completion_tokens": 340,
                "total_tokens": 460,
            },
            "executor": {
                "executor_type": "codex_skill",
                "executor_label": "codex-local",
                "skill_name": "8d-report-extraction-core",
                "skill_version": "draft-1",
            },
        }

    monkeypatch.setattr(client, "_post_with_retry", fake_post)

    result, usage = await client.complete_json(
        system_prompt="sys",
        user_prompt="user",
        response_model=ExtractionResult,
        request_context={
            "skill_name": "8d-report-extraction-core",
            "skill_version": "draft-1",
            "route_name": "full_report_single_pass",
            "prompt_modules": [
                "8d-report-extraction-core",
                "8d-actor-entity-typing",
                "8d-temporal-normalization",
                "8d-relationship-normalization",
                "8d-d4-root-cause-extraction",
            ],
        },
    )

    assert result.report is not None
    assert result.report.report_no == "FS-001"
    assert result.report.confidence == pytest.approx(0.91)
    assert usage.model == "codex-local"
    assert usage.metadata["provider"] == "codex"
    assert usage.metadata["skill_name"] == "8d-report-extraction-core"
    assert usage.metadata["skill_version"] == "draft-1"
    assert usage.metadata["route_name"] == "full_report_single_pass"
    assert usage.metadata["prompt_modules"] == [
        "8d-report-extraction-core",
        "8d-actor-entity-typing",
        "8d-temporal-normalization",
        "8d-relationship-normalization",
        "8d-d4-root-cause-extraction",
    ]


@pytest.mark.asyncio
async def test_codex_client_filters_invalid_relationship_endpoints_from_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = CodexClient(
        base_url="http://127.0.0.1:8787",
        extract_path="/extract",
        executor_label="codex-local",
    )

    async def fake_post(url: str, payload: dict) -> dict:
        assert url == "http://127.0.0.1:8787/extract"
        return {
            "data": {
                "report": {
                    "business_key": "FS-003",
                    "report_no": "FS-003",
                    "issue_title": "EP2002 阀门出厂测试泄漏",
                },
                "event": {
                    "business_key": "EVT-FS-003",
                    "event_id": "EVT-FS-003",
                    "event_type": "客诉",
                    "symptom": "密封面渗油",
                    "reporter_name": "克诺尔苏州",
                },
                "actions": [
                    {
                        "business_key": "ACT-FS-003-1",
                        "action_id": "ACT-FS-003-1",
                        "title": "更换为 Viton 材质 O 型圈",
                        "action_type": "纠正D5",
                    }
                ],
                "part_serials": [
                    {
                        "business_key": "OR-003::B2026-04",
                        "part_key": "OR-003::B2026-04",
                        "serial_number": "OR-003",
                    }
                ],
                "organizations": [
                    {
                        "business_key": "ORG-KNORR-SZ",
                        "org_code": "ORG-KNORR-SZ",
                        "org_name": "克诺尔苏州",
                        "org_type": "客户",
                    }
                ],
                "relationships": [
                    {
                        "from_label": "ProductEvent",
                        "from_key": "EVT-FS-003",
                        "to_label": "EightDReport",
                        "to_key": "FS-003",
                        "rel_type": "HAS_8D_REPORT",
                    },
                    {
                        "from_label": "ProductEvent",
                        "from_key": "EVT-FS-003",
                        "to_label": "Organization",
                        "to_key": "ORG-KNORR-SZ",
                        "rel_type": "RESPONSIBLE_ORG",
                    },
                    {
                        "from_label": "ActionItem",
                        "from_key": "ACT-FS-003-1",
                        "to_label": "PartSerial",
                        "to_key": "OR-003::B2026-04",
                        "rel_type": "TARGET_PRODUCT",
                    },
                ],
            }
        }

    monkeypatch.setattr(client, "_post_with_retry", fake_post)

    result, _usage = await client.complete_json(
        system_prompt="sys",
        user_prompt="user",
        response_model=ExtractionResult,
        request_context={
            "skill_name": "8d-report-extraction-core",
            "skill_version": "draft-1",
            "route_name": "full_report_single_pass",
            "prompt_modules": [
                "8d-report-extraction-core",
                "8d-actor-entity-typing",
                "8d-temporal-normalization",
                "8d-relationship-normalization",
                "8d-d2-event-extraction",
                "8d-d5-action-extraction",
            ],
        },
    )

    assert result.event is not None
    assert result.event.reporter_name == "克诺尔苏州"
    assert [rel.model_dump() for rel in result.relationships] == [
        {
            "from_label": "ProductEvent",
            "from_key": "EVT-FS-003",
            "to_label": "EightDReport",
            "to_key": "FS-003",
            "rel_type": "HAS_8D_REPORT",
            "properties": {},
        }
    ]


@pytest.mark.asyncio
async def test_fallback_llm_client_uses_secondary_provider() -> None:
    class FailingClient:
        async def complete_json(self, **kwargs):
            raise LLMError("primary unavailable")

    class SuccessClient:
        async def complete_json(self, **kwargs):
            return (
                ExtractionResult(
                    report=EightDReport(
                        business_key="FS-001",
                        report_no="FS-001",
                    )
                ),
                LLMUsage(
                    prompt_tokens=10,
                    completion_tokens=20,
                    total_tokens=30,
                    model="mock-v0.2",
                    metadata={"provider": "mock", "executor_type": "mock"},
                ),
            )

    client = FallbackLLMClient(
        primary=FailingClient(),
        fallback=SuccessClient(),
        primary_provider="codex",
        fallback_provider="mock",
    )

    result, usage = await client.complete_json(
        system_prompt="sys",
        user_prompt="user",
        response_model=ExtractionResult,
    )

    assert result.report is not None
    assert usage.metadata["primary_provider"] == "codex"
    assert usage.metadata["fallback_provider"] == "mock"
    assert "primary unavailable" in usage.metadata["fallback_trigger"]


@pytest.mark.asyncio
async def test_fallback_llm_client_falls_back_when_primary_times_out() -> None:
    class SlowPrimaryClient:
        async def complete_json(self, **kwargs):
            await asyncio.sleep(0.05)
            raise AssertionError("should timeout before returning")

    class SuccessClient:
        async def complete_json(self, **kwargs):
            return (
                ExtractionResult(
                    report=EightDReport(
                        business_key="FS-001",
                        report_no="FS-001",
                    )
                ),
                LLMUsage(
                    prompt_tokens=1,
                    completion_tokens=2,
                    total_tokens=3,
                    model="minimax",
                    metadata={"provider": "minimax", "executor_type": "minimax_llm"},
                ),
            )

    client = FallbackLLMClient(
        primary=SlowPrimaryClient(),
        fallback=SuccessClient(),
        primary_provider="codex",
        fallback_provider="minimax",
        primary_timeout_seconds=0.01,
    )

    result, usage = await client.complete_json(
        system_prompt="sys",
        user_prompt="user",
        response_model=ExtractionResult,
    )

    assert result.report is not None
    assert usage.metadata["primary_provider"] == "codex"
    assert usage.metadata["fallback_provider"] == "minimax"
    assert "timed out" in usage.metadata["fallback_trigger"]


@pytest.mark.asyncio
async def test_s4_extract_records_executor_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_context: dict = {}
    captured_prompt: dict = {}

    class FakeClient:
        async def complete_json(
            self,
            *,
            system_prompt: str,
            user_prompt: str,
            response_model: type[ExtractionResult],
            max_tokens: int = 4096,
            temperature: float = 0.1,
            request_context: dict | None = None,
        ) -> tuple[ExtractionResult, LLMUsage]:
            nonlocal captured_context
            nonlocal captured_prompt
            captured_context = request_context or {}
            captured_prompt = {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
            }
            return (
                ExtractionResult(
                    report=EightDReport(
                        business_key="FS-001",
                        report_no="FS-001",
                    )
                ),
                LLMUsage(
                    prompt_tokens=11,
                    completion_tokens=22,
                    total_tokens=33,
                    model="codex-local",
                    metadata={
                        "provider": "codex",
                        "executor_type": "codex_skill",
                        "skill_name": "8d-report-extraction-core",
                        "skill_version": "draft-2",
                        "route_name": "full_report_single_pass",
                    },
                ),
            )

    monkeypatch.setattr(settings, "llm_provider", "codex")
    monkeypatch.setattr(s4_extract, "get_llm_client", lambda: FakeClient())
    monkeypatch.setattr(s4_extract, "enrich_extraction_result", lambda er, report_id_hint=None: er)

    ctx = await s4_extract.run(_build_ctx())

    assert captured_context["route_name"] == "full_report_single_pass"
    assert captured_context["skill_name"] == settings.codex_skill_name
    assert captured_context["prompt_modules"] == [
        "8d-report-extraction-core",
        "8d-actor-entity-typing",
        "8d-temporal-normalization",
        "8d-relationship-normalization",
        "8d-d4-root-cause-extraction",
    ]
    assert "Skill Module: 8d-relationship-normalization" in captured_prompt["system_prompt"]
    assert "Skill Module: 8d-actor-entity-typing" in captured_prompt["system_prompt"]
    assert "Skill Module: 8d-d4-root-cause-extraction" in captured_prompt["system_prompt"]
    assert ctx.extraction_result is not None
    assert ctx.extraction_result.stats["executor_type"] == "codex_skill"
    assert ctx.extraction_result.stats["skill_name"] == "8d-report-extraction-core"
    assert ctx.extraction_result.stats["skill_version"] == "draft-2"
    assert ctx.extraction_result.stats["skill_modules"] == [
        "8d-report-extraction-core",
        "8d-actor-entity-typing",
        "8d-temporal-normalization",
        "8d-relationship-normalization",
        "8d-d4-root-cause-extraction",
    ]
