"""Codex 本地抽取服务客户端。

约定本地服务暴露一个 JSON API:
POST {base_url}{extract_path}

请求体:
{
  "system_prompt": "...",
  "user_prompt": "...",
  "response_model_name": "ExtractionResult",
  "response_schema": {...},
  "max_tokens": 8192,
  "temperature": 0.1,
  "request_context": {...}
}

响应体(推荐):
{
  "data": {...},
  "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
  "executor": {
    "executor_type": "codex_skill",
    "executor_label": "codex-local",
    "skill_name": "8d-report-extraction-core",
    "skill_version": "draft"
  }
}
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, TypeVar

import httpx
import structlog
from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from app.llm.base import LLMError, LLMUsage
from app.pipeline.relationship_builder import normalize_relationships_raw

T = TypeVar("T", bound=BaseModel)

logger = structlog.get_logger(__name__)


class _CodexExtractRequest(BaseModel):
    system_prompt: str
    user_prompt: str
    response_model_name: str
    response_schema: dict[str, Any]
    max_tokens: int = 4096
    temperature: float = 0.1
    request_context: dict[str, Any] = Field(default_factory=dict)


class CodexClient:
    """调用本地 Codex 抽取服务并返回结构化结果。"""

    def __init__(
        self,
        *,
        base_url: str,
        extract_path: str,
        timeout_seconds: int = 60,
        max_retries: int = 2,
        executor_label: str = "codex-local",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.extract_path = extract_path if extract_path.startswith("/") else f"/{extract_path}"
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.executor_label = executor_label

    async def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
        max_tokens: int = 4096,
        temperature: float = 0.1,
        request_context: dict[str, Any] | None = None,
    ) -> tuple[T, LLMUsage]:
        req = _CodexExtractRequest(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model_name=response_model.__name__,
            response_schema=response_model.model_json_schema(),
            max_tokens=max_tokens,
            temperature=temperature,
            request_context=request_context or {},
        )
        url = f"{self.base_url}{self.extract_path}"

        logger.info(
            "codex_request",
            url=url,
            response_model=response_model.__name__,
            skill_name=req.request_context.get("skill_name"),
            route_name=req.request_context.get("route_name"),
        )

        body = await self._post_with_retry(url, req.model_dump(mode="json"))
        raw_payload = body.get("data", body.get("result", body))
        payload = _decode_payload(raw_payload)
        payload = _drop_null_fields(payload)
        payload = normalize_relationships_raw(_coerce_types(payload))

        try:
            adapter = TypeAdapter(response_model)
            obj = adapter.validate_python(payload)
        except ValidationError as e:
            raise LLMError(f"Codex 返回不符合 {response_model.__name__} schema: {e}") from e

        usage_raw = body.get("usage", {})
        executor_raw = body.get("executor", {})
        metadata = {
            "provider": "codex",
            "executor_type": executor_raw.get("executor_type", "codex_skill"),
            "executor_label": executor_raw.get("executor_label", self.executor_label),
            "skill_name": executor_raw.get("skill_name") or req.request_context.get("skill_name"),
            "skill_version": executor_raw.get("skill_version")
            or req.request_context.get("skill_version"),
            "route_name": req.request_context.get("route_name"),
            "prompt_modules": req.request_context.get("prompt_modules", []),
            "base_url": self.base_url,
        }

        usage = LLMUsage(
            prompt_tokens=int(usage_raw.get("prompt_tokens", 0)),
            completion_tokens=int(usage_raw.get("completion_tokens", 0)),
            total_tokens=int(usage_raw.get("total_tokens", 0)),
            model=executor_raw.get("executor_label", self.executor_label),
            cost_estimate=float(usage_raw.get("cost_estimate", 0.0) or 0.0),
            metadata=metadata,
        )
        logger.info(
            "codex_response_ok",
            executor_label=usage.model,
            skill_name=metadata["skill_name"],
            skill_version=metadata["skill_version"],
            total_tokens=usage.total_tokens,
        )
        return obj, usage

    async def _post_with_retry(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        """指数退避重试 POST. 429/5xx 重试, 其他异常归一为 LLMError。"""
        last_err: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.post(url, json=payload)
                if response.status_code == 200:
                    return response.json()
                if response.status_code == 429 or response.status_code >= 500:
                    wait = 2 ** (attempt - 1)
                    logger.warning(
                        "codex_retry",
                        attempt=attempt,
                        status=response.status_code,
                        wait_seconds=wait,
                        body_preview=response.text[:300],
                    )
                    last_err = LLMError(f"Codex HTTP {response.status_code}: {response.text[:300]}")
                    if attempt < self.max_retries:
                        await asyncio.sleep(wait)
                    continue
                raise LLMError(
                    f"Codex HTTP {response.status_code} (不可重试): {response.text[:500]}"
                )
            except httpx.RequestError as e:
                wait = 2 ** (attempt - 1)
                logger.warning(
                    "codex_network_retry",
                    attempt=attempt,
                    error=str(e),
                    wait_seconds=wait,
                )
                last_err = LLMError(f"Codex 网络错误: {e}")
                if attempt < self.max_retries:
                    await asyncio.sleep(wait)
        raise last_err or LLMError("Codex 重试用尽 (未知原因)")


def _decode_payload(payload: Any) -> Any:
    """兼容 data/result 直接为 dict 或 JSON 字符串。"""
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except json.JSONDecodeError as e:
            raise LLMError(f"Codex 返回 data 不是合法 JSON: {e}") from e
    return payload


def _coerce_types(data: Any) -> Any:
    """递归把字符串形态的数字/布尔字段转回原生类型。"""
    if isinstance(data, dict):
        out: dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(value, str):
                if key == "confidence" or key.endswith("_score") or key.endswith("_probability"):
                    try:
                        out[key] = float(value)
                        continue
                    except ValueError:
                        pass
                if key.startswith("is_"):
                    if value.lower() in ("true", "1", "yes"):
                        out[key] = True
                        continue
                    if value.lower() in ("false", "0", "no"):
                        out[key] = False
                        continue
            out[key] = _coerce_types(value)
        return out
    if isinstance(data, list):
        return [_coerce_types(item) for item in data]
    return data


def _drop_null_fields(data: Any) -> Any:
    """递归去掉值为 null 的键, 让 Pydantic 默认值/默认工厂接管。"""
    if isinstance(data, dict):
        out: dict[str, Any] = {}
        for key, value in data.items():
            if value is None:
                continue
            out[key] = _drop_null_fields(value)
        return out
    if isinstance(data, list):
        return [_drop_null_fields(item) for item in data]
    return data
