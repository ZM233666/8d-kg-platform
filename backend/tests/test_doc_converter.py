"""doc 格式探测与转换。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.doc_converter import convert_legacy_doc_to_docx, open_as_docx
from app.services.doc_format import sniff_word_format

_DOC_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 512
_DOCX_MAGIC = b"PK\x03\x04" + b"\x00" * 512


def test_sniff_doc_and_docx() -> None:
    assert sniff_word_format(_DOC_MAGIC) == "doc"
    assert sniff_word_format(_DOCX_MAGIC) == "docx"
    assert sniff_word_format(b"not a word file") is None


def test_open_as_docx_passthrough_docx(tmp_path: Path) -> None:
    src = tmp_path / "a.docx"
    src.write_bytes(_DOCX_MAGIC)
    with open_as_docx(src) as out:
        assert out == src


def test_open_as_docx_converts_doc(tmp_path: Path) -> None:
    src = tmp_path / "legacy.doc"
    src.write_bytes(_DOC_MAGIC)
    dst = tmp_path / "out.docx"
    dst.write_bytes(_DOCX_MAGIC)

    def fake_convert(s: Path, d: Path) -> None:
        assert s == src
        d.write_bytes(_DOCX_MAGIC)

    with patch("app.services.doc_converter.convert_legacy_doc_to_docx", side_effect=fake_convert):
        with open_as_docx(src) as out:
            assert out.exists()
            assert sniff_word_format(out.read_bytes()) == "docx"


def test_convert_legacy_doc_raises_when_all_backends_fail(tmp_path: Path) -> None:
    src = tmp_path / "legacy.doc"
    src.write_bytes(_DOC_MAGIC)
    dst = tmp_path / "out.docx"

    with patch("app.services.doc_converter._converter_chain", return_value=[]):
        with pytest.raises(RuntimeError, match="无法将 .doc 转为"):
            convert_legacy_doc_to_docx(src, dst)
