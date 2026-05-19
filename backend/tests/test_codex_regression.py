"""Codex 抽取回归测试：模拟真实 8D 报告风格场景。"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from app.core.config import settings
from app.llm.base import LLMUsage
from app.pipeline import s4_extract
from app.pipeline.context import PipelineContext
from app.schemas.extraction import ExtractionResult

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "codex_regression"


def _load_regression_fixture(name: str) -> dict:
    path = FIXTURE_DIR / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _build_context(scenario: dict) -> PipelineContext:
    context = dict(scenario["context"])
    context["document_id"] = str(uuid4())
    return PipelineContext.model_validate(context)


class _FakeScenarioClient:
    def __init__(self, scenario: dict) -> None:
        self._scenario = scenario
        self.calls: list[dict] = []

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
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "request_context": request_context or {},
            }
        )
        return (
            response_model.model_validate(self._scenario["llm_result"]),
            LLMUsage(
                prompt_tokens=100,
                completion_tokens=200,
                total_tokens=300,
                model="codex-local",
                metadata={
                    "provider": "codex",
                    "executor_type": "codex_skill",
                    "skill_name": "8d-report-extraction-core",
                    "skill_version": "regression-1",
                    "route_name": "full_report_single_pass",
                },
            ),
        )


async def _run_scenario(
    monkeypatch: pytest.MonkeyPatch,
    fixture_name: str,
) -> tuple[dict, _FakeScenarioClient, PipelineContext]:
    scenario = _load_regression_fixture(fixture_name)
    client = _FakeScenarioClient(scenario)

    monkeypatch.setattr(settings, "llm_provider", "codex")
    monkeypatch.setattr(s4_extract, "get_llm_client", lambda: client)

    ctx = await s4_extract.run(_build_context(scenario))
    return scenario, client, ctx


@pytest.mark.asyncio
async def test_codex_regression_reporter_org_confusion_stays_conservative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _scenario, client, ctx = await _run_scenario(monkeypatch, "reporter_org_confusion")

    assert client.calls, "fake client should be invoked"
    request_context = client.calls[0]["request_context"]
    assert request_context["prompt_modules"] == [
        "8d-report-extraction-core",
        "8d-actor-entity-typing",
        "8d-temporal-normalization",
        "8d-relationship-normalization",
        "8d-d2-event-extraction",
    ]

    result = ctx.extraction_result
    assert result is not None
    assert result.event is not None
    assert result.event.reporter_name == "克诺尔苏州"
    rel_types = {rel.rel_type for rel in result.relationships}
    assert rel_types == {"HAS_8D_REPORT"}
    assert not any(rel.rel_type == "RESPONSIBLE_ORG" for rel in result.relationships)
    assert result.stats["skill_modules"] == [
        "8d-report-extraction-core",
        "8d-actor-entity-typing",
        "8d-temporal-normalization",
        "8d-relationship-normalization",
        "8d-d2-event-extraction",
    ]


@pytest.mark.asyncio
async def test_codex_regression_mixed_report_keeps_mainline_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _scenario, client, ctx = await _run_scenario(monkeypatch, "mixed_mainline_report")

    assert client.calls, "fake client should be invoked"
    request_context = client.calls[0]["request_context"]
    assert request_context["prompt_modules"] == [
        "8d-report-extraction-core",
        "8d-actor-entity-typing",
        "8d-temporal-normalization",
        "8d-relationship-normalization",
        "8d-d2-event-extraction",
        "8d-d4-root-cause-extraction",
        "8d-d5-action-extraction",
    ]

    result = ctx.extraction_result
    assert result is not None
    rel_keys = {(rel.from_label, rel.rel_type, rel.to_label) for rel in result.relationships}
    assert ("ProductEvent", "HAS_8D_REPORT", "EightDReport") in rel_keys
    assert ("ProductEvent", "RELATED_FAILURE_MODE", "FailureMode") in rel_keys
    assert ("EightDReport", "ROOT_CAUSE", "CauseItem") in rel_keys
    assert ("EightDReport", "CORRECTIVE_ACTION", "ActionItem") in rel_keys
    assert ("PartSerial", "SUPPLIED_BY", "Organization") in rel_keys
    assert ("ActionItem", "VERIFIES_CAUSE", "CauseItem") in rel_keys
    assert ("EightDReport", "RESPONSIBLE_ORG", "Organization") not in rel_keys
    assert result.stats["skill_modules"] == [
        "8d-report-extraction-core",
        "8d-actor-entity-typing",
        "8d-temporal-normalization",
        "8d-relationship-normalization",
        "8d-d2-event-extraction",
        "8d-d4-root-cause-extraction",
        "8d-d5-action-extraction",
    ]


@pytest.mark.asyncio
async def test_codex_regression_temporal_ambiguity_keeps_datetime_fields_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _scenario, client, ctx = await _run_scenario(monkeypatch, "temporal_ambiguity_dual_stage")

    assert client.calls, "fake client should be invoked"
    request_context = client.calls[0]["request_context"]
    assert request_context["prompt_modules"] == [
        "8d-report-extraction-core",
        "8d-actor-entity-typing",
        "8d-temporal-normalization",
        "8d-relationship-normalization",
        "8d-d2-event-extraction",
        "8d-d5-action-extraction",
    ]

    result = ctx.extraction_result
    assert result is not None
    assert result.event is not None
    assert result.event.occurred_at is None
    assert result.actions
    assert all(action.due_date is None for action in result.actions)
    rel_keys = {(rel.from_label, rel.rel_type, rel.to_label) for rel in result.relationships}
    assert ("ProductEvent", "HAS_8D_REPORT", "EightDReport") in rel_keys
    assert ("EightDReport", "CORRECTIVE_ACTION", "ActionItem") in rel_keys
    assert result.stats["skill_modules"] == [
        "8d-report-extraction-core",
        "8d-actor-entity-typing",
        "8d-temporal-normalization",
        "8d-relationship-normalization",
        "8d-d2-event-extraction",
        "8d-d5-action-extraction",
    ]


@pytest.mark.asyncio
async def test_codex_regression_temporal_resolution_positive_keeps_explicit_business_times(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _scenario, client, ctx = await _run_scenario(monkeypatch, "temporal_resolution_positive")

    assert client.calls, "fake client should be invoked"
    request_context = client.calls[0]["request_context"]
    assert request_context["prompt_modules"] == [
        "8d-report-extraction-core",
        "8d-actor-entity-typing",
        "8d-temporal-normalization",
        "8d-relationship-normalization",
        "8d-d2-event-extraction",
        "8d-d5-action-extraction",
    ]

    result = ctx.extraction_result
    assert result is not None
    assert result.report is not None
    assert result.event is not None
    assert result.actions

    assert result.report.closed_at is not None
    assert result.report.closed_at.isoformat() == "2025-07-30T00:00:00+00:00"
    assert result.event.occurred_at is not None
    assert result.event.occurred_at.isoformat() == "2025-07-20T00:00:00+00:00"
    assert result.actions[0].completed_at is not None
    assert result.actions[0].completed_at.isoformat() == "2025-07-28T00:00:00+00:00"
    assert result.actions[0].due_date is None
    assert result.stats["skill_modules"] == [
        "8d-report-extraction-core",
        "8d-actor-entity-typing",
        "8d-temporal-normalization",
        "8d-relationship-normalization",
        "8d-d2-event-extraction",
        "8d-d5-action-extraction",
    ]


@pytest.mark.asyncio
async def test_codex_regression_multi_actor_org_roles_keeps_only_runtime_safe_edges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _scenario, client, ctx = await _run_scenario(monkeypatch, "multi_actor_org_roles")

    assert client.calls, "fake client should be invoked"
    request_context = client.calls[0]["request_context"]
    assert request_context["prompt_modules"] == [
        "8d-report-extraction-core",
        "8d-actor-entity-typing",
        "8d-temporal-normalization",
        "8d-relationship-normalization",
        "8d-d2-event-extraction",
        "8d-d5-action-extraction",
    ]

    result = ctx.extraction_result
    assert result is not None
    rel_keys = {
        (rel.from_label, rel.from_key, rel.rel_type, rel.to_label, rel.to_key)
        for rel in result.relationships
    }
    assert (
        "ActionItem",
        "ACT-REG-004-1",
        "RESPONSIBLE_ORG",
        "Organization",
        "ORG-QA-004",
    ) in rel_keys
    assert (
        "PartSerial",
        "OR-REG-004::B2026-05",
        "SUPPLIED_BY",
        "Organization",
        "ORG-SUP-004",
    ) in rel_keys
    assert (
        "ProductEvent",
        "EVT-FS-REG-004",
        "RESPONSIBLE_ORG",
        "Organization",
        "ORG-CUST-004",
    ) not in rel_keys
    assert ("EightDReport", "RESPONSIBLE_ORG", "Organization") not in {
        (rel.from_label, rel.rel_type, rel.to_label) for rel in result.relationships
    }


@pytest.mark.asyncio
async def test_codex_regression_symptom_only_scene_does_not_invent_failure_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _scenario, client, ctx = await _run_scenario(monkeypatch, "symptom_only_no_failure_mode")

    assert client.calls, "fake client should be invoked"
    request_context = client.calls[0]["request_context"]
    assert request_context["prompt_modules"] == [
        "8d-report-extraction-core",
        "8d-actor-entity-typing",
        "8d-temporal-normalization",
        "8d-relationship-normalization",
        "8d-d2-event-extraction",
    ]

    result = ctx.extraction_result
    assert result is not None
    assert result.failure_modes == []
    rel_keys = {(rel.from_label, rel.rel_type, rel.to_label) for rel in result.relationships}
    assert ("ProductEvent", "HAS_8D_REPORT", "EightDReport") in rel_keys
    assert ("ProductEvent", "HAPPENED_ON", "ProductInstance") in rel_keys
    assert ("ProductEvent", "RELATED_FAILURE_MODE", "FailureMode") not in rel_keys


@pytest.mark.asyncio
async def test_codex_regression_real_ep2002_derived_report_keeps_mainline_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario, client, ctx = await _run_scenario(
        monkeypatch, "real_ep2002_secondary_regulator_derived"
    )

    assert scenario["source_kind"] == "real_derived"
    assert client.calls, "fake client should be invoked"
    request_context = client.calls[0]["request_context"]
    assert request_context["prompt_modules"] == [
        "8d-report-extraction-core",
        "8d-actor-entity-typing",
        "8d-temporal-normalization",
        "8d-relationship-normalization",
        "8d-d2-event-extraction",
        "8d-d4-root-cause-extraction",
        "8d-d5-action-extraction",
    ]

    result = ctx.extraction_result
    assert result is not None
    assert result.event is not None
    assert result.event.reporter_name == "客户调试团队"
    rel_keys = {
        (rel.from_label, rel.from_key, rel.rel_type, rel.to_label, rel.to_key)
        for rel in result.relationships
    }
    assert (
        "ProductEvent",
        "EVT-FS-REAL-001",
        "HAS_8D_REPORT",
        "EightDReport",
        "FS-REAL-001",
    ) in rel_keys
    assert (
        "ProductEvent",
        "EVT-FS-REAL-001",
        "RELATED_FAILURE_MODE",
        "FailureMode",
        "FM-REAL-001",
    ) in rel_keys
    assert ("EightDReport", "FS-REAL-001", "ROOT_CAUSE", "CauseItem", "CAU-REAL-001-1") in rel_keys
    assert (
        "EightDReport",
        "FS-REAL-001",
        "CORRECTIVE_ACTION",
        "ActionItem",
        "ACT-REAL-001-1",
    ) in rel_keys
    assert (
        "EightDReport",
        "FS-REAL-001",
        "CORRECTIVE_ACTION",
        "ActionItem",
        "ACT-REAL-001-2",
    ) in rel_keys
    assert (
        "EightDReport",
        "FS-REAL-001",
        "PREVENTIVE_ACTION",
        "ActionItem",
        "ACT-REAL-001-3",
    ) in rel_keys
    assert (
        "ActionItem",
        "ACT-REAL-001-4",
        "RESPONSIBLE_ORG",
        "Organization",
        "ORG-REAL-001-SUP",
    ) in rel_keys
    assert (
        "EightDReport",
        "FS-REAL-001",
        "RESPONSIBLE_ORG",
        "Organization",
        "ORG-REAL-001-SUP",
    ) not in rel_keys


@pytest.mark.asyncio
async def test_codex_regression_real_foshan_derived_report_stays_conservative_on_weak_root_cause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario, client, ctx = await _run_scenario(monkeypatch, "real_foshan_spring_fracture_derived")

    assert scenario["source_kind"] == "real_derived"
    assert client.calls, "fake client should be invoked"
    request_context = client.calls[0]["request_context"]
    assert request_context["prompt_modules"] == [
        "8d-report-extraction-core",
        "8d-actor-entity-typing",
        "8d-temporal-normalization",
        "8d-relationship-normalization",
        "8d-d2-event-extraction",
        "8d-d4-root-cause-extraction",
        "8d-d5-action-extraction",
    ]

    result = ctx.extraction_result
    assert result is not None
    assert result.causes == []
    assert result.organizations == []
    assert result.actions
    assert all(action.due_date is None for action in result.actions)
    rel_keys = {(rel.from_label, rel.rel_type, rel.to_label) for rel in result.relationships}
    assert ("ProductEvent", "HAS_8D_REPORT", "EightDReport") in rel_keys
    assert ("ProductEvent", "RELATED_FAILURE_MODE", "FailureMode") in rel_keys
    assert ("EightDReport", "CORRECTIVE_ACTION", "ActionItem") in rel_keys
    assert ("EightDReport", "ROOT_CAUSE", "CauseItem") not in rel_keys
    assert ("EightDReport", "RESPONSIBLE_ORG", "Organization") not in rel_keys
