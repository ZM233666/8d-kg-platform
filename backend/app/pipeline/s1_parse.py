"""s1 Parser (Reader)：从 MinIO / 本地读取 docx 并解析为 raw_text / raw_tables / raw_images。"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

import structlog
from docx import Document
from docx.oxml import CT_P, CT_Tbl
from docx.oxml.ns import qn

from app.pipeline.base import stage
from app.pipeline.context import PipelineContext
from app.services.minio_client import download_to_tempfile, parse_minio_url

logger = structlog.get_logger(__name__)

HEADING_RE = re.compile(r"^Heading(\d+)$", re.IGNORECASE)


def _style_level_from_xml(p_elem) -> int | None:
    """直接从 CT_P XML 读 pStyle val，避免 python-docx style.name 失效问题。"""
    pPr = p_elem.find(qn("w:pPr"))
    if pPr is None:
        return None
    pStyle = pPr.find(qn("w:pStyle"))
    if pStyle is None:
        return None
    val = pStyle.get(qn("w:val")) or ""
    m = HEADING_RE.match(val.strip())
    return int(m.group(1)) if m else None


def _para_text(p_elem) -> str:
    """从 CT_P 提取所有 w:t 文本。"""
    texts = p_elem.xpath(".//w:t")
    return "".join(t.text or "" for t in texts).strip()


def _load_local_docx(path: str) -> Document:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Local docx not found: {p}")
    return Document(str(p))


def _tbl_to_dict(table, section_path: list[str], raw_index: int) -> dict:
    hdr = [c.text.strip() for c in table.rows[0].cells] if table.rows else []
    rows = []
    for row in table.rows[1:]:
        rows.append(dict(zip(hdr, [c.text.strip() for c in row.cells])))
    return {"section_path": section_path.copy(), "headers": hdr, "rows": rows, "raw_index": raw_index}


@stage("s1_parse")
async def run(ctx: PipelineContext) -> PipelineContext:
    """从 ctx.minio_key 读取 docx，解析为 raw_text / raw_tables / raw_images。"""
    parsed = urlparse(ctx.minio_key)
    scheme = parsed.scheme

    if scheme == "local":
        docx_path = ctx.minio_key[len("local://") :]
        doc = _load_local_docx(docx_path)
    elif scheme == "minio":
        tmp_path = await download_to_tempfile(ctx.minio_key)
        try:
            doc = _load_local_docx(str(tmp_path))
        finally:
            tmp_path.unlink(missing_ok=True)
    else:
        raise ValueError(f"Unsupported minio_key scheme: {scheme}")

    section_path: list[str] = []
    raw_tables: list[dict] = []
    raw_text_parts: list[str] = []
    last_sec_marker = ""

    body = doc.element.body
    t_idx = 0  # doc.tables index

    for child in body:
        if isinstance(child, CT_P):
            level = _style_level_from_xml(child)
            if level is not None:
                heading_text = _para_text(child)
                if heading_text:
                    section_path = section_path[: level - 1] + [heading_text]
                    marker = "\n[SEC:" + "/".join(section_path) + "]\n\n"
                    if marker != last_sec_marker:
                        raw_text_parts.append(marker)
                        last_sec_marker = marker
            else:
                text = _para_text(child)
                if text:
                    raw_text_parts.append(text + "\n\n")
        elif isinstance(child, CT_Tbl):
            if t_idx < len(doc.tables):
                tbl_dict = _tbl_to_dict(doc.tables[t_idx], section_path, t_idx)
                raw_tables.append(tbl_dict)
            t_idx += 1

    ctx.raw_text = "".join(raw_text_parts).strip()
    ctx.raw_tables = raw_tables
    ctx.raw_images = []

    logger.info(
        "s1_parse.done",
        text_len=len(ctx.raw_text),
        tables=len(ctx.raw_tables),
        images=len(ctx.raw_images),
    )
    return ctx
