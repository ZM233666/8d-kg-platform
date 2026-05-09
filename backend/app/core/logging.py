"""structlog 全局配置：JSON 输出 + trace_id 上下文。"""

import logging
import sys
import uuid
from contextlib import contextmanager
from typing import Any

import structlog
from structlog.types import Processor

from app.core.config import settings


def add_trace_id(logger: Any, method_name: str, event_dict: dict) -> dict:
    """在 event_dict 中注入 trace_id（如果上下文中没有则自动生成）。"""
    if "trace_id" not in event_dict:
        event_dict["trace_id"] = _get_trace_id()
    return event_dict


_trace_id_context = {}


def _get_trace_id() -> str:
    return _trace_id_context.get("trace_id", str(uuid.uuid4()))


@contextmanager
def trace_id_context(trace_id: str):
    """设置当前 trace_id 上下文（with 子句内有效）。"""
    old = _trace_id_context.get("trace_id")
    _trace_id_context["trace_id"] = trace_id
    try:
        yield
    finally:
        if old is None:
            _trace_id_context.pop("trace_id", None)
        else:
            _trace_id_context["trace_id"] = old


def setup_logging() -> None:
    """配置 structlog：JSON 格式输出到 stdout，trace_id 自动注入。"""
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
        add_trace_id,
    ]

    structlog.configure(
        processors=shared_processors
        + [
            structlog.processors.JSONRenderer()
            if not settings.debug
            else structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    # 抑制 uvicorn 自身的访问日志（保留 error 级别）
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.ERROR)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """返回一个带 __name__ 的 structlog logger。"""
    return structlog.get_logger(name)
