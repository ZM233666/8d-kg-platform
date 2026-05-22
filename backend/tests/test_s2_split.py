"""s2_split 约束测试: 整份文档应只产出一个 chunk。"""

from __future__ import annotations

from uuid import uuid4

import pytest
from app.pipeline.context import PipelineContext
from app.pipeline.s2_split import FULL_DOCUMENT_ROLE, FULL_DOCUMENT_SECTION
from app.pipeline.s2_split import run as split_run


@pytest.mark.asyncio
async def test_s2_split_keeps_whole_document_as_single_chunk() -> None:
    """即使原文含章节标记, 也不再按章节切成多个 chunk。"""

    raw_text = (
        "[SEC:问题描述]\n"
        "第一段问题描述。\n\n"
        "[SEC:根本原因分析]\n"
        "第二段根因分析。\n\n"
        "[SEC:纠正措施]\n"
        "第三段纠正措施。"
    )
    ctx = PipelineContext(
        document_id=uuid4(),
        minio_key="minio://kg-documents/uploads/20260515/demo.docx",
        report_id_hint="RPT-001",
        raw_text=raw_text,
    )

    out = await split_run(ctx)

    assert len(out.chunks) == 1
    chunk = out.chunks[0]
    assert chunk.chunk_id == "RPT-001#full_document#0"
    assert chunk.report_id == "RPT-001"
    assert chunk.section_path == FULL_DOCUMENT_SECTION
    assert chunk.chunk_role == FULL_DOCUMENT_ROLE
    assert chunk.para_idx == 0
    assert chunk.text == raw_text


@pytest.mark.asyncio
async def test_s2_split_falls_back_to_unknown_report_id() -> None:
    """没有 report_id_hint 时, 应使用 UNKNOWN 构造唯一 chunk。"""

    ctx = PipelineContext(
        document_id=uuid4(),
        minio_key="minio://kg-documents/uploads/20260515/demo.docx",
        raw_text="整篇 8D 报告正文。",
    )

    out = await split_run(ctx)

    assert len(out.chunks) == 1
    chunk = out.chunks[0]
    assert chunk.chunk_id == "UNKNOWN#full_document#0"
    assert chunk.report_id == "UNKNOWN"
    assert chunk.section_path == FULL_DOCUMENT_SECTION
    assert chunk.chunk_role == FULL_DOCUMENT_ROLE
    assert chunk.text == "整篇 8D 报告正文。"


@pytest.mark.asyncio
async def test_s2_split_keeps_plaintext_document_intact() -> None:
    """纯文本报告也应完整保留到单个 chunk 中。"""

    raw_text = (
        "封面信息\n\n"
        "问题描述\n\n"
        "出现压力超差现象。\n\n"
        "根本原因分析\n\n"
        "活塞销存在孔洞并最终变形。\n\n"
        "纠正措施\n\n"
        "对库存活塞销进行100%外观检。"
    )
    ctx = PipelineContext(
        document_id=uuid4(),
        minio_key="minio://kg-documents/uploads/20260515/demo.docx",
        report_id_hint="RPT-003",
        raw_text=raw_text,
    )

    out = await split_run(ctx)

    assert len(out.chunks) == 1
    chunk = out.chunks[0]
    assert chunk.chunk_id == "RPT-003#full_document#0"
    assert chunk.section_path == FULL_DOCUMENT_SECTION
    assert chunk.chunk_role == FULL_DOCUMENT_ROLE
    assert chunk.text == raw_text
