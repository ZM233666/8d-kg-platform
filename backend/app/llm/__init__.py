"""LLM 客户端抽象层 + 工厂。

v0.3 骨架阶段：通过 settings.llm_provider 切换 mock / minimax / codex，
并支持可选 fallback provider。
"""

from app.core.config import settings
from app.llm.base import LLMClient, LLMError, LLMUsage
from app.llm.codex_client import CodexClient
from app.llm.fallback_client import FallbackLLMClient
from app.llm.mock_client import MockLLMClient
from app.llm.minimax_client import MinimaxClient

__all__ = [
    "LLMClient",
    "LLMUsage",
    "LLMError",
    "MockLLMClient",
    "MinimaxClient",
    "CodexClient",
    "FallbackLLMClient",
    "effective_llm_model",
    "build_llm_client",
    "get_llm_client",
]


def effective_llm_model(provider: str | None = None) -> str:
    """写入 extraction_run 与 stats 时使用的模型名。"""
    provider = (provider or settings.llm_provider or "mock").lower()
    if provider == "mock":
        return "mock-v0.1"
    if provider == "minimax":
        return settings.llm_model_default or "MiniMax-M2.7"
    if provider == "codex":
        return settings.codex_executor_label or "codex-local"
    return settings.llm_model_default or provider


def build_llm_client(provider: str) -> LLMClient:
    """按 provider 构造单个客户端实例。"""
    provider_normalized = (provider or "mock").lower()
    if provider_normalized == "mock":
        return MockLLMClient()
    if provider_normalized == "minimax":
        return MinimaxClient(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model_default,
            timeout_seconds=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
        )
    if provider_normalized == "codex":
        return CodexClient(
            base_url=settings.codex_base_url,
            extract_path=settings.codex_extract_path,
            timeout_seconds=settings.codex_timeout_seconds,
            max_retries=settings.codex_max_retries,
            executor_label=settings.codex_executor_label,
        )
    raise LLMError(
        f"未知 llm_provider: {provider_normalized!r}（支持: mock / minimax / codex）"
    )


def get_llm_client() -> LLMClient:
    """按 settings.llm_provider 返回 LLM 客户端实例。

    - 'mock' → MockLLMClient（默认）
    - 'minimax' → MinimaxClient（需配置 llm_api_key / llm_base_url / llm_model_default）
    - 'codex' → CodexClient（调用本地 Codex 抽取服务）
    """
    provider = (settings.llm_provider or "mock").lower()
    client = build_llm_client(provider)

    fallback_provider = (settings.llm_fallback_provider or "").strip().lower()
    if fallback_provider and fallback_provider != provider:
        return FallbackLLMClient(
            primary=client,
            fallback=build_llm_client(fallback_provider),
            primary_provider=provider,
            fallback_provider=fallback_provider,
        )
    return client
