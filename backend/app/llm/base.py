"""LLM 客户端协议 + 通用类型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """LLM 调用层统一异常。"""


@dataclass(frozen=True)
class LLMUsage:
    """单次调用的 token / cost 计量。"""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model: str = "mock"
    cost_estimate: float = 0.0
    metadata: dict = field(default_factory=dict)


class LLMClient(Protocol):
    """所有 LLM 客户端必须实现的协议。

    输出必须用 Pydantic 模型强制 schema，不接受 free-form text。
    """

    async def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
        max_tokens: int = 4096,
        temperature: float = 0.1,
    ) -> tuple[T, LLMUsage]:
        """返回 (Pydantic 实例, usage)。"""
        ...