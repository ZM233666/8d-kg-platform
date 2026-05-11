"""固定样本 Mock LLM 客户端。

行为：忽略输入 prompt，按 response_model 名分发返回 fixtures/sample_extraction.json 对应字段。
所有调用记 fake usage（tokens=200/400/600，cost=0）。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import TypeVar, get_args, get_origin

from pydantic import BaseModel, TypeAdapter, ValidationError

from app.llm.base import LLMClient, LLMError, LLMUsage

T = TypeVar("T", bound=BaseModel)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_extraction.json"


@lru_cache(maxsize=1)
def _load_fixture() -> dict:
    if not FIXTURE_PATH.exists():
        raise LLMError(f"Mock fixture not found: {FIXTURE_PATH}")
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _resolve_fixture_key(response_model: type, action_type_hint: str | None = None) -> str:
    """根据 response_model 类型和可选 hint 解析 fixture key。"""
    origin = get_origin(response_model)
    if origin is list:
        inner = get_args(response_model)[0]
        base_name = inner.__name__
        if base_name == "ActionEvent" and action_type_hint:
            return f"ActionEvent_{action_type_hint}_list"
        return f"{base_name}_list"
    return response_model.__name__


class MockLLMClient(LLMClient):
    """v0.1 固定样本 mock。

    构造时可传 action_type_hint（containment/corrective/preventive）覆盖 ActionEvent 列表分发。
    """

    def __init__(self, action_type_hint: str | None = None):
        self._action_type_hint = action_type_hint
        self._calls = 0

    async def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
        max_tokens: int = 4096,
        temperature: float = 0.1,
    ) -> tuple[T, LLMUsage]:
        self._calls += 1
        fixture = _load_fixture()
        key = _resolve_fixture_key(response_model, self._action_type_hint)
        if key not in fixture:
            raise LLMError(
                f"Mock fixture missing key '{key}' for response_model {response_model}"
            )

        raw = fixture[key]
        try:
            adapter = TypeAdapter(response_model)
            obj = adapter.validate_python(raw)
        except ValidationError as e:
            raise LLMError(f"Mock fixture validation failed for {key}: {e}") from e

        usage = LLMUsage(
            prompt_tokens=200,
            completion_tokens=400,
            total_tokens=600,
            model="mock-v0.1",
            cost_estimate=0.0,
            metadata={"fixture_key": key, "call_index": self._calls},
        )
        return obj, usage