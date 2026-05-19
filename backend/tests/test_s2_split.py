"""s2_split 约束测试: 按章节路径切分为多个 chunk。"""

from __future__ import annotations

from uuid import uuid4

import pytest
from app.pipeline.context import PipelineContext
from app.pipeline.s2_split import run as split_run


@pytest.mark.asyncio
async def test_s2_split_routes_chunks_by_section(monkeypatch: pytest.MonkeyPatch) -> None:
    """显式章节标记应还原为 section_path 和 chunk_role。"""

    monkeypatch.setattr(
        "app.pipeline.s2_split.load_lexicon",
        lambda: {
            "chapter_routing": {
                "defect": ["问题描述"],
                "root_cause": ["根本原因分析"],
                "corrective_action": ["纠正措施"],
            },
            "chapter_role_mapping": {
                "defect": "evidence",
                "root_cause": "hypothesis",
                "corrective_action": "action",
            },
        },
    )

    ctx = PipelineContext(
        document_id=uuid4(),
        minio_key="minio://kg-documents/uploads/20260515/demo.docx",
        report_id_hint="RPT-001",
        raw_text=(
            "[SEC:问题描述]\n"
            "第一段问题描述。\n\n"
            "[SEC:根本原因分析]\n"
            "第二段根因分析。\n\n"
            "[SEC:纠正措施]\n"
            "第三段纠正措施。"
        ),
    )

    out = await split_run(ctx)

    assert len(out.chunks) == 3
    assert [chunk.section_path for chunk in out.chunks] == [
        ["问题描述"],
        ["根本原因分析"],
        ["纠正措施"],
    ]
    assert [chunk.chunk_role for chunk in out.chunks] == ["evidence", "hypothesis", "action"]
    assert [chunk.para_idx for chunk in out.chunks] == [0, 1, 2]
    assert all(chunk.report_id == "RPT-001" for chunk in out.chunks)
    assert out.chunks[0].text == "第一段问题描述。"
    assert out.chunks[1].text == "第二段根因分析。"
    assert out.chunks[2].text == "第三段纠正措施。"


@pytest.mark.asyncio
async def test_s2_split_falls_back_to_unknown_without_section_markers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """没有章节标记时, 应回退到 unknown section。"""

    monkeypatch.setattr("app.pipeline.s2_split.load_lexicon", lambda: {})

    ctx = PipelineContext(
        document_id=uuid4(),
        minio_key="minio://kg-documents/uploads/20260515/demo.docx",
        report_id_hint="RPT-002",
        raw_text="这是一段没有章节标记的正文。\n\n仍然需要被切成可处理的 chunk。",
    )

    out = await split_run(ctx)

    assert len(out.chunks) == 1
    chunk = out.chunks[0]
    assert chunk.report_id == "RPT-002"
    assert chunk.section_path == ["unknown"]
    assert chunk.chunk_role == "unknown"
    assert "没有章节标记" in chunk.text


@pytest.mark.asyncio
async def test_s2_split_detects_plaintext_headings_without_sec_markers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """没有 [SEC] 标记时, 仍应从纯文本标题里识别章节。"""

    monkeypatch.setattr(
        "app.pipeline.s2_split.load_lexicon",
        lambda: {
            "chapter_routing": {
                "defect": ["问题描述"],
                "root_cause": ["根本原因分析"],
                "corrective_action": ["纠正措施"],
            },
            "chapter_role_mapping": {
                "defect": "evidence",
                "root_cause": "hypothesis",
                "corrective_action": "action",
            },
        },
    )

    ctx = PipelineContext(
        document_id=uuid4(),
        minio_key="minio://kg-documents/uploads/20260515/demo.docx",
        report_id_hint="RPT-003",
        raw_text=(
            "封面信息\n\n"
            "目录\n\n"
            "1问题描述6\n\n"
            "2根本原因分析8\n\n"
            "问题描述\n\n"
            "出现压力超差现象。\n\n"
            "根本原因分析\n\n"
            "活塞销存在孔洞并最终变形。\n\n"
            "纠正措施\n\n"
            "对库存活塞销进行100%外观检。"
        ),
    )

    out = await split_run(ctx)

    assert len(out.chunks) == 4
    assert [chunk.section_path for chunk in out.chunks] == [
        ["unknown"],
        ["问题描述"],
        ["根本原因分析"],
        ["纠正措施"],
    ]
    assert [chunk.chunk_role for chunk in out.chunks] == [
        "unknown",
        "evidence",
        "hypothesis",
        "action",
    ]
    assert "目录" in out.chunks[0].text
    assert out.chunks[1].text == "出现压力超差现象。"
    assert out.chunks[2].text == "活塞销存在孔洞并最终变形。"


@pytest.mark.asyncio
async def test_s2_split_applies_subsection_role_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    """子章节 override 应覆盖父章节默认 role。"""

    monkeypatch.setattr(
        "app.pipeline.s2_split.load_lexicon",
        lambda: {
            "chapter_routing": {
                "root_cause": ["根本原因分析"],
            },
            "chapter_role_mapping": {
                "root_cause": "hypothesis",
            },
            "sub_section_role_overrides": {
                "结构": "background",
                "功能检测": "evidence",
                "实验结论": "conclusion",
            },
        },
    )

    ctx = PipelineContext(
        document_id=uuid4(),
        minio_key="minio://kg-documents/uploads/20260515/demo.docx",
        report_id_hint="RPT-004",
        raw_text=(
            "[SEC:根本原因分析/结构]\n"
            "结构说明正文。\n\n"
            "[SEC:根本原因分析/功能检测]\n"
            "功能检测正文。\n\n"
            "[SEC:根本原因分析/实验结论]\n"
            "实验结论正文。"
        ),
    )

    out = await split_run(ctx)

    assert [chunk.section_path for chunk in out.chunks] == [
        ["根本原因分析", "结构"],
        ["根本原因分析", "功能检测"],
        ["根本原因分析", "实验结论"],
    ]
    assert [chunk.chunk_role for chunk in out.chunks] == ["background", "evidence", "conclusion"]


@pytest.mark.asyncio
async def test_s2_split_prefers_more_specific_subsection_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """更长的 subsection override 应优先于短关键词。"""

    monkeypatch.setattr(
        "app.pipeline.s2_split.load_lexicon",
        lambda: {
            "chapter_routing": {
                "root_cause": ["根本原因分析"],
            },
            "chapter_role_mapping": {
                "root_cause": "hypothesis",
            },
            "sub_section_role_overrides": {
                "功能": "background",
                "功能检测": "evidence",
            },
        },
    )

    ctx = PipelineContext(
        document_id=uuid4(),
        minio_key="minio://kg-documents/uploads/20260515/demo.docx",
        report_id_hint="RPT-005",
        raw_text="[SEC:根本原因分析/功能检测]\n功能检测正文。",
    )

    out = await split_run(ctx)

    assert len(out.chunks) == 1
    assert out.chunks[0].section_path == ["根本原因分析", "功能检测"]
    assert out.chunks[0].chunk_role == "evidence"
