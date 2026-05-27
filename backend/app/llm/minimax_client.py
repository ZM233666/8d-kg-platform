"""MiniMax LLM 客户端（OpenAI 兼容协议）。"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, TypeVar

import httpx
import structlog
from pydantic import BaseModel, TypeAdapter, ValidationError

from app.llm.base import LLMError, LLMUsage
from app.pipeline.relationship_builder import normalize_relationships_raw

T = TypeVar("T", bound=BaseModel)

logger = structlog.get_logger(__name__)


class MinimaxClient:
    """MiniMax OpenAI-compatible 客户端。"""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: int = 60,
        max_retries: int = 3,
    ) -> None:
        if not api_key or api_key.startswith("sk-placeholder"):
            raise LLMError(
                "MinimaxClient: api_key 未配置或为占位符，请在 .env 中设置 MINIMAX_API_KEY"
            )
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

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
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        logger.info(
            "minimax_request",
            model=self.model,
            base_url=self.base_url,
            response_model=response_model.__name__,
            prompt_len=len(system_prompt) + len(user_prompt),
        )

        body = await self._post_with_retry(url, headers, payload)

        try:
            content = body["choices"][0]["message"]["content"]
            usage_raw = body.get("usage", {})
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError(
                f"MiniMax 响应结构异常：缺少 choices[0].message.content；body={body}"
            ) from e

        content = _strip_think_tags(content)
        content = _strip_code_fence(content)

        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            preview = content[:500]
            raise LLMError(f"MiniMax 返回非合法 JSON: {e}; content preview: {preview!r}") from e

        data = _drop_null_fields(data)
        data = _coerce_types(data)
        data = normalize_relationships_raw(data)

        try:
            adapter = TypeAdapter(response_model)
            obj = adapter.validate_python(data)
        except ValidationError as e:
            raise LLMError(f"MiniMax 响应不符合 {response_model.__name__} schema: {e}") from e

        usage = LLMUsage(
            prompt_tokens=int(usage_raw.get("prompt_tokens", 0)),
            completion_tokens=int(usage_raw.get("completion_tokens", 0)),
            total_tokens=int(usage_raw.get("total_tokens", 0)),
            model=self.model,
            cost_estimate=0.0,
            metadata={
                "provider": "minimax",
                "executor_type": "minimax_llm",
                "base_url": self.base_url,
                "request_context": request_context or {},
            },
        )
        logger.info(
            "minimax_response_ok",
            model=self.model,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
        )
        return obj, usage

    async def _post_with_retry(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """指数退避重试 POST。429/5xx 重试，其他 4xx 直接失败。"""
        last_err: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as cli:
                    response = await cli.post(url, headers=headers, json=payload)
                if response.status_code == 200:
                    return response.json()
                if response.status_code == 429 or response.status_code >= 500:
                    wait = 2 ** (attempt - 1)
                    logger.warning(
                        "minimax_retry",
                        attempt=attempt,
                        status=response.status_code,
                        wait_seconds=wait,
                        body_preview=response.text[:300],
                    )
                    last_err = LLMError(
                        f"MiniMax HTTP {response.status_code}: {response.text[:300]}"
                    )
                    if attempt < self.max_retries:
                        await asyncio.sleep(wait)
                    continue
                raise LLMError(
                    f"MiniMax HTTP {response.status_code} (不可重试): {response.text[:500]}"
                )
            except httpx.RequestError as e:
                wait = 2 ** (attempt - 1)
                logger.warning(
                    "minimax_network_retry",
                    attempt=attempt,
                    error=str(e),
                    wait_seconds=wait,
                )
                last_err = LLMError(f"MiniMax 网络错误: {e}")
                if attempt < self.max_retries:
                    await asyncio.sleep(wait)
        raise last_err or LLMError("MiniMax 重试用尽（未知原因）")


_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def _strip_think_tags(content: str) -> str:
    return _THINK_RE.sub("", content).strip()


_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", re.DOTALL)


def _strip_code_fence(content: str) -> str:
    matched = _FENCE_RE.match(content.strip())
    return matched.group(1).strip() if matched else content


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
    """递归去掉 null 字段，让 Pydantic 默认值接管。"""
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
