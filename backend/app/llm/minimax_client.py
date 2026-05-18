"""MiniMax LLM 客户端（OpenAI 兼容协议）。

通过 OpenAI 兼容 chat/completions endpoint 调用 MiniMax 模型。
- 强制 JSON mode（response_format: json_object）
- 把 response_model 的字段约束写进 system prompt 引导
- 指数退避重试（429/5xx，最多 N 次）
- 异常归一为 LLMError
- 容错预处理：confidence 字符串→float，is_* 字符串→bool
"""

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
    """MiniMax OpenAI 兼容客户端。

    实现 LLMClient 协议（Protocol，不需要继承）。
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: int = 60,
        max_retries: int = 3,
    ):
        if not api_key or api_key.startswith("sk-placeholder"):
            raise LLMError(
                "MinimaxClient: api_key 未配置或为占位符，请在 .env 中设置 LLM_API_KEY"
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
    ) -> tuple[T, LLMUsage]:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        # MiniMax M 系列不支持 response_format，靠 prompt 引导 JSON 输出
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

        # 取出 content
        try:
            content = body["choices"][0]["message"]["content"]
            usage_raw = body.get("usage", {})
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError(
                f"MiniMax 响应结构异常：缺少 choices[0].message.content；body={body}"
            ) from e

        # 剥可能的 <think>...</think> 标签（M 系列推理模型遗留行为）
        content = _strip_think_tags(content)
        # 剥可能的 ```json ... ``` markdown code fence
        content = _strip_code_fence(content)

        # 解析 JSON
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            preview = content[:500]
            raise LLMError(
                f"MiniMax 返回非合法 JSON: {e}; content preview: {preview!r}"
            ) from e

        # 容错预处理
        data = _coerce_types(data)
        data = normalize_relationships_raw(data)

        # 用 Pydantic 校验
        try:
            adapter = TypeAdapter(response_model)
            obj = adapter.validate_python(data)
        except ValidationError as e:
            raise LLMError(
                f"MiniMax 响应不符合 {response_model.__name__} schema: {e}"
            ) from e

        usage = LLMUsage(
            prompt_tokens=int(usage_raw.get("prompt_tokens", 0)),
            completion_tokens=int(usage_raw.get("completion_tokens", 0)),
            total_tokens=int(usage_raw.get("total_tokens", 0)),
            model=self.model,
            cost_estimate=0.0,
            metadata={"provider": "minimax", "base_url": self.base_url},
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
        self, url: str, headers: dict, payload: dict
    ) -> dict:
        """指数退避重试 POST。429/5xx 重试，4xx 其他直接 fail。"""
        last_err: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as cli:
                    r = await cli.post(url, headers=headers, json=payload)
                if r.status_code == 200:
                    return r.json()
                # 429 / 5xx：可重试
                if r.status_code == 429 or r.status_code >= 500:
                    wait = 2 ** (attempt - 1)
                    logger.warning(
                        "minimax_retry",
                        attempt=attempt,
                        status=r.status_code,
                        wait_seconds=wait,
                        body_preview=r.text[:300],
                    )
                    last_err = LLMError(
                        f"MiniMax HTTP {r.status_code}: {r.text[:300]}"
                    )
                    if attempt < self.max_retries:
                        await asyncio.sleep(wait)
                    continue
                # 4xx 其他：直接抛
                raise LLMError(
                    f"MiniMax HTTP {r.status_code} (不可重试): {r.text[:500]}"
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
        # 重试用尽
        raise last_err or LLMError("MiniMax 重试用尽（未知原因）")


# ---------- helpers ----------

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def _strip_think_tags(content: str) -> str:
    """去掉 M 系列推理模型可能输出的 <think>...</think> 块。"""
    return _THINK_RE.sub("", content).strip()


_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", re.DOTALL)


def _strip_code_fence(content: str) -> str:
    """去掉 ```json ... ``` markdown code fence。"""
    m = _FENCE_RE.match(content.strip())
    return m.group(1).strip() if m else content


def _coerce_types(data: Any) -> Any:
    """递归把字符串形态的数字/布尔字段转回原生类型。

    覆盖范围：
      - 字段名以 'confidence' / '_score' / '_probability' 结尾 → float
      - 字段名以 'is_' 开头 → bool
    其他字段不动，避免误伤。
    """
    if isinstance(data, dict):
        out = {}
        for k, v in data.items():
            if isinstance(v, str):
                if k == "confidence" or k.endswith("_score") or k.endswith("_probability"):
                    try:
                        out[k] = float(v)
                        continue
                    except ValueError:
                        pass
                if k.startswith("is_"):
                    if v.lower() in ("true", "1", "yes"):
                        out[k] = True
                        continue
                    if v.lower() in ("false", "0", "no"):
                        out[k] = False
                        continue
            out[k] = _coerce_types(v)
        return out
    if isinstance(data, list):
        return [_coerce_types(x) for x in data]
    return data
