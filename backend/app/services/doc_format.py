"""Word 文档格式探测（.docx zip vs 旧版 .doc OLE）。"""

from __future__ import annotations

from pathlib import Path

_DOCX_MAGIC = b"PK\x03\x04"
_LEGACY_DOC_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def sniff_word_format(data: bytes) -> str | None:
    """返回 'docx' | 'doc' | None。"""
    if len(data) >= 4 and data[:4] == _DOCX_MAGIC:
        return "docx"
    if len(data) >= 8 and data[:8] == _LEGACY_DOC_MAGIC:
        return "doc"
    return None


def read_sniff_word_format(path: Path, *, nbytes: int = 8) -> str | None:
    with path.open("rb") as f:
        return sniff_word_format(f.read(nbytes))


INVALID_DOCX_MSG = "文件不是有效的 Word 文档（需为 .doc 或 .docx 格式）"
