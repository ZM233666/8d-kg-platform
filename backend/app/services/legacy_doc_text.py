"""旧版 .doc 文本兜底解析。

当 `.doc -> .docx` 转换失败时, 尽量从原始二进制中恢复可读文本,
保证 Reader 至少能拿到正文继续走后续 pipeline。
"""

from __future__ import annotations

import re
from pathlib import Path

_CONTROL_TO_NEWLINE = str.maketrans(
    {
        "\r": "\n",
        "\x0b": "\n",
        "\x0c": "\n",
        "\x07": "\n",
        "\t": "\n",
    }
)

_NOISE_PATTERNS = (
    re.compile(r"^DOCPROPERTY\b", re.IGNORECASE),
    re.compile(r"^MERGEFORMAT\b", re.IGNORECASE),
    re.compile(r"^HYPERLINK\b", re.IGNORECASE),
    re.compile(r"^PAGEREF\b", re.IGNORECASE),
    re.compile(r"^Toc\d+$", re.IGNORECASE),
)
_MEANINGFUL_CHAR_RE = re.compile(r"[A-Za-z0-9\u4e00-\u9fff]")
_MOSTLY_SYMBOL_RE = re.compile(r"^[^A-Za-z0-9\u4e00-\u9fff]{8,}$")
_MAX_LINE_LEN = 300
_MIN_LINE_LEN = 2
_MAX_OUTPUT_CHARS = 220_000


def extract_text_from_legacy_doc(path: Path) -> str:
    """从旧版 `.doc` 原始字节中提取尽可能可读的文本。"""
    raw = path.read_bytes().decode("utf-16le", errors="ignore")
    normalized = raw.translate(_CONTROL_TO_NEWLINE)
    normalized = re.sub(r"[\x00-\x08\x0e-\x1f]", " ", normalized)
    normalized = normalized.replace("\u0014", " ").replace("\u0015", " ")
    normalized = normalized.replace("\u0013", " ").replace("\u0001", " ")

    parts = [part.strip() for part in re.split(r"\n+", normalized)]
    cleaned: list[str] = []
    last = ""
    seen: set[str] = set()
    total_chars = 0
    for part in parts:
        item = " ".join(part.split())
        if len(item) < _MIN_LINE_LEN or len(item) > _MAX_LINE_LEN:
            continue
        if _is_noise(item):
            continue
        if item in seen:
            continue
        meaningful = len(_MEANINGFUL_CHAR_RE.findall(item))
        if meaningful == 0:
            continue
        if meaningful / len(item) < 0.35:
            continue
        if _MOSTLY_SYMBOL_RE.match(item):
            continue
        if item == last:
            continue
        cleaned.append(item)
        seen.add(item)
        last = item
        total_chars += len(item) + 1
        if total_chars >= _MAX_OUTPUT_CHARS:
            break
    return "\n".join(cleaned).strip()


def _is_noise(text: str) -> bool:
    if not text:
        return True
    if all(ch in "-_=*·. " for ch in text):
        return True
    return any(pattern.search(text) for pattern in _NOISE_PATTERNS)
