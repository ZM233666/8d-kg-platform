"""LLM 客户端抽象层 + 工厂。

v0.2: 通过 settings.llm_provider 切换 mock / minimax。
"""

from app.core.config import settings
from app.llm.base import LLMClient, LLMError, LLMUsage
from app.llm.mock_client import MockLLMClient
from app.llm.minimax_client import MinimaxClient

__all__ = [
    "LLMClient",
    "LLMUsage",
    "LLMError",
    "MockLLMClient",
    "MinimaxClient",
    "effective_llm_model",
    "get_llm_client",
]


def effective_llm_model() -> str:
    """写入 extraction_run 与 stats 时使用的模型名。"""
    provider = (settings.llm_provider or "mock").lower()
    if provider == "mock":
        return "mock-v0.1"
    return settings.llm_model_default or "MiniMax-M2.7"


def get_llm_client() -> LLMClient:
    """按 settings.llm_provider 返回 LLM 客户端实例。

    - 'mock' → MockLLMClient（默认）
    - 'minimax' → MinimaxClient（需配置 llm_api_key / llm_base_url / llm_model_default）
    """
    provider = (settings.llm_provider or "mock").lower()
    if provider == "mock":
        return MockLLMClient()
    if provider == "minimax":
        return MinimaxClient(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model_default,
            timeout_seconds=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
        )
    raise LLMError(
        f"未知 llm_provider: {provider!r}（支持: mock / minimax）"
    )
