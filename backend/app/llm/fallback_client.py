"""LLM fallback 包装器。

在主 provider 失败时自动降级到备用 provider，并把降级信息写入 usage.metadata。
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, TypeVar

from pydantic import BaseModel

from app.llm.base import LLMClient, LLMError, LLMUsage

T = TypeVar("T", bound=BaseModel)


class FallbackLLMClient:
    """主/备双 provider 包装器。"""

    def __init__(
        self,
        *,
        primary: LLMClient,
        fallback: LLMClient,
        primary_provider: str,
        fallback_provider: str,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.primary_provider = primary_provider
        self.fallback_provider = fallback_provider

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
        try:
            return await self.primary.complete_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=response_model,
                max_tokens=max_tokens,
                temperature=temperature,
                request_context=request_context,
            )
        except LLMError as primary_error:
            result, usage = await self.fallback.complete_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=response_model,
                max_tokens=max_tokens,
                temperature=temperature,
                request_context=request_context,
            )
            metadata = dict(usage.metadata)
            metadata["primary_provider"] = self.primary_provider
            metadata["fallback_provider"] = self.fallback_provider
            metadata["fallback_trigger"] = str(primary_error)
            metadata.setdefault("provider", self.fallback_provider)
            metadata.setdefault("executor_type", self.fallback_provider)
            return result, replace(usage, metadata=metadata)
