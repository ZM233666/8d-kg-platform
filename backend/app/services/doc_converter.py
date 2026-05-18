"""旧版 .doc → .docx 转换（供 python-docx 解析）。"""

from __future__ import annotations

import platform
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

import structlog

from app.services.doc_format import INVALID_DOCX_MSG, read_sniff_word_format

logger = structlog.get_logger(__name__)

DOC_CONVERT_FAILED_MSG = (
    "无法将 .doc 转为 .docx：请在运行 Celery Worker 的机器安装 LibreOffice（命令行 soffice），"
    "macOS 开发环境可使用系统自带的 textutil"
)

_ConverterFn = Callable[[Path, Path], None]


def _convert_with_textutil(src: Path, dst: Path) -> None:
    if platform.system() != "Darwin":
        raise OSError("textutil is only available on macOS")
    textutil = shutil.which("textutil") or "/usr/bin/textutil"
    subprocess.run(
        [textutil, "-convert", "docx", "-output", str(dst), str(src)],
        check=True,
        capture_output=True,
        text=True,
        timeout=180,
    )


def _convert_with_soffice(src: Path, dst: Path) -> None:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise FileNotFoundError("soffice / libreoffice not found in PATH")
    outdir = dst.parent
    subprocess.run(
        [
            soffice,
            "--headless",
            "--convert-to",
            "docx",
            "--outdir",
            str(outdir),
            str(src),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=300,
    )
    produced = outdir / f"{src.stem}.docx"
    if not produced.exists():
        raise FileNotFoundError(f"LibreOffice did not produce {produced}")
    if produced.resolve() != dst.resolve():
        produced.replace(dst)


def _converter_chain() -> list[tuple[str, _ConverterFn]]:
    chain: list[tuple[str, _ConverterFn]] = []
    if platform.system() == "Darwin":
        chain.append(("textutil", _convert_with_textutil))
    chain.append(("libreoffice", _convert_with_soffice))
    return chain


def convert_legacy_doc_to_docx(src: Path, dst: Path) -> None:
    """将 .doc 转为 dst 路径的 .docx；失败时抛出 RuntimeError。"""
    errors: list[str] = []
    for name, fn in _converter_chain():
        try:
            fn(src, dst)
            if dst.exists() and dst.stat().st_size > 0:
                logger.info("doc_converter.ok", backend=name, src=str(src), dst=str(dst))
                return
            errors.append(f"{name}: output empty")
        except Exception as exc:
            errors.append(f"{name}: {exc}")
    raise RuntimeError(f"{DOC_CONVERT_FAILED_MSG} ({'; '.join(errors)})")


@contextmanager
def open_as_docx(source: Path) -> Iterator[Path]:
    """若 source 为 .doc 则转换到临时 .docx 后 yield；已是 .docx 则直接 yield。"""
    fmt = read_sniff_word_format(source)
    if fmt == "docx":
        yield source
        return
    if fmt != "doc":
        raise ValueError(INVALID_DOCX_MSG)

    tmp = Path(tempfile.mkstemp(suffix=".docx")[1])
    try:
        convert_legacy_doc_to_docx(source, tmp)
        yield tmp
    finally:
        tmp.unlink(missing_ok=True)
