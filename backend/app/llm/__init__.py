"""LLM 客户端抽象层 + 工厂。"""

from app.core.config import settings
from app.llm.base import LLMClient, LLMError, LLMUsage
from app.llm.codex_client import CodexClient
from app.llm.fallback_client import FallbackLLMClient
from app.llm.minimax_client import MinimaxClient
from app.llm.mock_client import MockLLMClient

__all__ = [
    "CodexClient",
    "FallbackLLMClient",
    "LLMClient",
    "LLMError",
    "LLMUsage",
    "MinimaxClient",
    "MockLLMClient",
    "build_llm_client",
    "effective_llm_model",
    "get_llm_client",
]


def effective_llm_model(provider: str | None = None) -> str:
    """写入 extraction_run 与 stats 时使用的模型名。"""
    provider = (provider or settings.llm_provider or "mock").lower()
    if provider == "mock":
        return "mock-v0.1"
    if provider == "codex":
        return settings.codex_executor_label or "codex-local"
    if provider == "minimax":
        return settings.minimax_model or "minimax"
    return provider


def build_llm_client(provider: str) -> LLMClient:
    """按 provider 构造单个客户端实例。"""
    provider_normalized = (provider or "mock").lower()
    if provider_normalized == "mock":
        return MockLLMClient()
    if provider_normalized == "codex":
        return CodexClient(
            base_url=settings.codex_base_url,
            extract_path=settings.codex_extract_path,
            timeout_seconds=settings.codex_timeout_seconds,
            max_retries=settings.codex_max_retries,
            executor_label=settings.codex_executor_label,
        )
    if provider_normalized == "minimax":
        return MinimaxClient(
            api_key=settings.minimax_api_key,
            base_url=settings.minimax_base_url,
            model=settings.minimax_model,
            timeout_seconds=settings.minimax_timeout_seconds,
            max_retries=settings.minimax_max_retries,
        )
    raise LLMError(
        f"未知 llm_provider: {provider_normalized!r} (支持: mock / codex / minimax)"
    )


def get_llm_client() -> LLMClient:
    """按 settings.llm_provider 返回 LLM 客户端实例。

    - 'mock' → MockLLMClient (默认)
    - 'codex' → CodexClient (调用本地 Codex 抽取服务)
    - 'minimax' → MinimaxClient (OpenAI-compatible endpoint)
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
            primary_timeout_seconds=settings.llm_primary_soft_timeout_seconds,
        )
    return client
