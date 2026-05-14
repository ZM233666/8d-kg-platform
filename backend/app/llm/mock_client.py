"""固定样本 Mock LLM 客户端（v0.2）。

v0.2 简化：MockLLMClient.complete_json 总是返回整个 ExtractionResult（从 sample_extraction.json 加载）。
不再按 response_model 名分发到不同 key——v0.2 s4_extract 只调一次 LLM。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, TypeAdapter, ValidationError

from app.llm.base import LLMClient, LLMError, LLMUsage

T = TypeVar("T", bound=BaseModel)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_extraction.json"


@lru_cache(maxsize=1)
def _load_fixture() -> dict:
    if not FIXTURE_PATH.exists():
        raise LLMError(f"Mock fixture not found: {FIXTURE_PATH}")
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


class MockLLMClient(LLMClient):
    """v0.2 固定样本 mock。返回整个 ExtractionResult，忽略 prompt 内容。"""

    def __init__(self):
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

        # v0.2 mock 只支持 ExtractionResult；其他 response_model 视为未实现
        if response_model.__name__ != "ExtractionResult":
            raise LLMError(
                f"MockLLMClient v0.2 only supports response_model=ExtractionResult, got {response_model.__name__}"
            )

        # 取 fixture 顶层（除 _meta 外的所有键应组成完整 ExtractionResult dict）
        payload = {k: v for k, v in fixture.items() if not k.startswith("_")}

        try:
            adapter = TypeAdapter(response_model)
            obj = adapter.validate_python(payload)
        except ValidationError as e:
            raise LLMError(f"Mock fixture validation failed for ExtractionResult: {e}") from e

        usage = LLMUsage(
            prompt_tokens=1600,
            completion_tokens=3200,
            total_tokens=4800,
            cost_estimate=0.0,
            metadata={"model": "mock-v0.2", "call_index": self._calls},
        )
        return obj, usage