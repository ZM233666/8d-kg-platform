"""Lexicon 模块：加载领域词典。"""

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

LEXICON_PATH = Path(__file__).parent / "domain_lexicon.yaml"


@lru_cache(maxsize=1)
def load_lexicon() -> dict[str, Any]:
    """加载领域词典，结果被 LRU 缓存。"""
    if not LEXICON_PATH.exists():
        raise FileNotFoundError(f"Lexicon file not found: {LEXICON_PATH}")
    with LEXICON_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def reload_lexicon() -> dict[str, Any]:
    """清缓存后重新加载（开发/测试用）。"""
    load_lexicon.cache_clear()
    return load_lexicon()


__all__ = ["LEXICON_PATH", "load_lexicon", "reload_lexicon"]
