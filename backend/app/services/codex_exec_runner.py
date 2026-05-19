"""本地 Codex CLI 执行器。

把结构化抽取请求转换为 `codex exec` 调用, 并将最终 JSON 结果回传给 HTTP 服务层。
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog
from pydantic import BaseModel, Field

from app.core.config import settings
from app.llm.codex_output_schema import build_codex_output_schema

logger = structlog.get_logger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]


class CodexExtractorRequest(BaseModel):
    """本地 Codex 抽取服务请求体。"""

    system_prompt: str
    user_prompt: str
    response_model_name: str
    response_schema: dict[str, Any]
    max_tokens: int = 4096
    temperature: float = 0.1
    request_context: dict[str, Any] = Field(default_factory=dict)


class CodexExecutorMetadata(BaseModel):
    """执行器元信息。"""

    executor_type: str = "codex_skill"
    executor_label: str = "codex-local"
    skill_name: str = "8d-report-extraction-core"
    skill_version: str = "draft"


class CodexExtractorResponse(BaseModel):
    """本地 Codex 抽取服务响应体。"""

    data: Any
    usage: dict[str, int | float] = Field(default_factory=dict)
    executor: CodexExecutorMetadata


@dataclass(slots=True)
class _CodexExecArtifacts:
    schema_path: Path
    output_path: Path


class CodexExecError(RuntimeError):
    """Codex CLI 执行失败。"""


class CodexExecRunner:
    """调用本地 `codex exec` 完成一次结构化抽取。"""

    def __init__(
        self,
        *,
        cli_path: str,
        workdir: str,
        timeout_seconds: int,
        model: str | None = None,
        executor_label: str = "codex-local",
    ) -> None:
        self.cli_path = cli_path
        self.workdir = workdir
        self.timeout_seconds = timeout_seconds
        self.model = model
        self.executor_label = executor_label

    async def extract(self, req: CodexExtractorRequest) -> CodexExtractorResponse:
        """执行一次 Codex 结构化抽取。"""
        with tempfile.TemporaryDirectory(prefix="codex-extract-") as tmpdir:
            artifacts = self._prepare_artifacts(
                Path(tmpdir),
                response_model_name=req.response_model_name,
                schema=req.response_schema,
            )
            prompt = self._build_prompt(req)
            cmd = self._build_command(artifacts, prompt)

            logger.info(
                "codex_exec.start",
                cli_path=self.cli_path,
                workdir=self.workdir,
                skill_name=req.request_context.get("skill_name"),
                route_name=req.request_context.get("route_name"),
            )

            stdout, stderr, returncode = await self._run_command(cmd)
            if returncode != 0:
                raise CodexExecError(
                    "Codex CLI 执行失败:"
                    f"exit={returncode}, stderr={self._tail(stderr)}, stdout={self._tail(stdout)}"
                )

            if not artifacts.output_path.exists():
                raise CodexExecError("Codex CLI 未产出 output-last-message 文件")

            raw = artifacts.output_path.read_text(encoding="utf-8").strip()
            if not raw:
                raise CodexExecError("Codex CLI 输出为空")

            data = self._decode_output(raw)
            executor = CodexExecutorMetadata(
                executor_label=self.executor_label,
                skill_name=str(req.request_context.get("skill_name") or settings.codex_skill_name),
                skill_version=str(
                    req.request_context.get("skill_version") or settings.codex_skill_version
                ),
            )
            logger.info(
                "codex_exec.ok",
                skill_name=executor.skill_name,
                skill_version=executor.skill_version,
            )
            return CodexExtractorResponse(
                data=data,
                usage={
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "cost_estimate": 0.0,
                },
                executor=executor,
            )

    def _prepare_artifacts(
        self,
        tmpdir: Path,
        *,
        response_model_name: str,
        schema: dict[str, Any],
    ) -> _CodexExecArtifacts:
        schema_path = tmpdir / "response_schema.json"
        output_path = tmpdir / "last_message.json"
        codex_schema = build_codex_output_schema(response_model_name, schema)
        schema_path.write_text(
            json.dumps(_strictify_json_schema(codex_schema), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return _CodexExecArtifacts(schema_path=schema_path, output_path=output_path)

    def _build_command(self, artifacts: _CodexExecArtifacts, prompt: str) -> list[str]:
        cmd = [
            self.cli_path,
            "exec",
            "--skip-git-repo-check",
            "--ephemeral",
            "--color",
            "never",
            "-s",
            "read-only",
            "-C",
            self.workdir,
            "--output-schema",
            str(artifacts.schema_path),
            "-o",
            str(artifacts.output_path),
        ]
        if self.model:
            cmd.extend(["-m", self.model])
        cmd.append(prompt)
        return cmd

    def _build_prompt(self, req: CodexExtractorRequest) -> str:
        request_context_json = json.dumps(
            req.request_context,
            ensure_ascii=False,
            indent=2,
        )
        return (
            "你现在是 8D 报告结构化抽取执行器。\n"
            "必须严格遵守 JSON Schema, 只输出最终 JSON 对象, 不要输出解释、Markdown、思考过程。\n\n"
            "【System Prompt】\n"
            f"{req.system_prompt}\n\n"
            "【Request Context】\n"
            f"{request_context_json}\n\n"
            "【User Prompt】\n"
            f"{req.user_prompt}\n"
        )

    async def _run_command(self, cmd: list[str]) -> tuple[str, str, int]:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.workdir,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout_seconds,
            )
        except TimeoutError as exc:
            process.kill()
            await process.communicate()
            raise CodexExecError(f"Codex CLI 超时 (>{self.timeout_seconds}s)") from exc
        return (
            stdout_bytes.decode("utf-8", errors="replace"),
            stderr_bytes.decode("utf-8", errors="replace"),
            int(process.returncode or 0),
        )

    def _decode_output(self, raw: str) -> Any:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw

    def _tail(self, text: str, *, limit: int = 600) -> str:
        text = text.strip()
        return text[-limit:] if len(text) > limit else text


def build_codex_exec_runner() -> CodexExecRunner:
    """从 settings 构造默认 runner。"""
    return CodexExecRunner(
        cli_path=settings.codex_cli_path,
        workdir=settings.codex_exec_workdir or str(_PROJECT_ROOT),
        timeout_seconds=settings.codex_timeout_seconds,
        model=settings.codex_exec_model,
        executor_label=settings.codex_executor_label,
    )


def _strictify_json_schema(node: Any) -> Any:
    """把 Pydantic JSON Schema 收紧为 Codex `--output-schema` 可接受的形式。"""
    if isinstance(node, dict):
        strict_node = {key: _strictify_json_schema(value) for key, value in node.items()}
        if strict_node.get("type") == "object":
            strict_node.setdefault("additionalProperties", False)
            properties = strict_node.get("properties", {})
            original_required = set(strict_node.get("required", []))
            strict_properties: dict[str, Any] = {}
            for key, value in properties.items():
                if key not in original_required:
                    strict_properties[key] = _make_nullable_schema(value)
                else:
                    strict_properties[key] = value
            strict_node["properties"] = strict_properties
            strict_node["required"] = list(strict_properties.keys())
        return strict_node
    if isinstance(node, list):
        return [_strictify_json_schema(item) for item in node]
    return node


def _make_nullable_schema(schema: Any) -> Any:
    """将非 required 属性包装成允许 null 的 schema。"""
    if not isinstance(schema, dict):
        return {"anyOf": [schema, {"type": "null"}]}
    if schema.get("type") == "null":
        return schema
    if "anyOf" in schema and any(
        isinstance(option, dict) and option.get("type") == "null" for option in schema["anyOf"]
    ):
        return schema
    return {"anyOf": [schema, {"type": "null"}]}
