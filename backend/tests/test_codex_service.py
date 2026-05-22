"""本地 Codex 抽取服务测试。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import anyio
from app.codex_service import app
from app.services.codex_exec_runner import (
    CodexExecError,
    CodexExecRunner,
    CodexExtractorRequest,
    CodexExtractorResponse,
    _make_nullable_schema,
    _strictify_json_schema,
)
from fastapi.testclient import TestClient


class _FakeRunner(CodexExecRunner):
    async def _run_command(self, cmd: list[str], prompt: str) -> tuple[str, str, int]:
        output_index = cmd.index("-o") + 1
        output_path = Path(cmd[output_index])
        assert cmd[-1] == "-"
        assert "抽取这份报告" in prompt
        await anyio.Path(output_path).write_text(
            json.dumps({"report": None, "event": None, "relationships": []}),
            encoding="utf-8",
        )
        return "", "", 0


class _FailRunner(CodexExecRunner):
    async def _run_command(self, cmd: list[str], prompt: str) -> tuple[str, str, int]:
        return "", "boom", 1


def _build_request() -> CodexExtractorRequest:
    return CodexExtractorRequest(
        system_prompt="只输出 JSON",
        user_prompt="抽取这份报告",
        response_model_name="ExtractionResult",
        response_schema={"type": "object"},
        request_context={
            "skill_name": "8d-report-extraction-core",
            "skill_version": "draft",
            "route_name": "full_report_single_pass",
        },
    )


async def test_codex_exec_runner_returns_structured_response() -> None:
    runner = _FakeRunner(
        cli_path="codex",
        workdir=".",
        timeout_seconds=30,
        executor_label="codex-local",
    )

    response = await runner.extract(_build_request())

    assert isinstance(response, CodexExtractorResponse)
    assert response.data == {"report": None, "event": None, "relationships": []}
    assert response.executor.executor_type == "codex_skill"
    assert response.executor.executor_label == "codex-local"
    assert response.executor.skill_name == "8d-report-extraction-core"


async def test_codex_exec_runner_raises_for_cli_failure() -> None:
    runner = _FailRunner(
        cli_path="codex",
        workdir=".",
        timeout_seconds=30,
        executor_label="codex-local",
    )

    try:
        await runner.extract(_build_request())
    except CodexExecError as exc:
        assert "Codex CLI 执行失败" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("expected CodexExecError")


def test_codex_service_health() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_codex_service_extract_returns_502_on_runner_error() -> None:
    with TestClient(app) as client:
        app.state.codex_runner = _FailRunner(
            cli_path="codex",
            workdir=".",
            timeout_seconds=30,
            executor_label="codex-local",
        )
        response = client.post(
            "/extract",
            json=_build_request().model_dump(mode="json"),
        )

    assert response.status_code == 502
    assert "Codex CLI 执行失败" in response.json()["detail"]


def test_codex_service_extract_returns_runner_payload() -> None:
    with TestClient(app) as client:
        app.state.codex_runner = _FakeRunner(
            cli_path="codex",
            workdir=".",
            timeout_seconds=30,
            executor_label="codex-local",
        )
        response = client.post(
            "/extract",
            json=_build_request().model_dump(mode="json"),
        )

    body: dict[str, Any] = response.json()
    assert response.status_code == 200
    assert body["data"]["relationships"] == []
    assert body["executor"]["executor_label"] == "codex-local"


def test_strictify_json_schema_adds_additional_properties_false() -> None:
    schema = {
        "type": "object",
        "properties": {
            "inner": {
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                },
            }
        },
    }

    strict_schema = _strictify_json_schema(schema)

    assert strict_schema["additionalProperties"] is False
    inner_schema = strict_schema["properties"]["inner"]["anyOf"][0]
    assert inner_schema["additionalProperties"] is False
    assert strict_schema["required"] == ["inner"]
    assert inner_schema["required"] == ["message"]


def test_make_nullable_schema_wraps_optional_property() -> None:
    nullable = _make_nullable_schema({"type": "string"})

    assert nullable == {"anyOf": [{"type": "string"}, {"type": "null"}]}
