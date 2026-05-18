"""s2_split 约束测试：整份报告只产出 1 个 chunk。"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.pipeline.context import PipelineContext
from app.pipeline.s2_split import run as split_run


@pytest.mark.asyncio
async def test_s2_split_keeps_one_chunk(monkeypatch: pytest.MonkeyPatch) -> None:
    """不论正文多长，s2 都应保留为单个报告级 chunk。"""

    monkeypatch.setattr("app.pipeline.s2_split.load_lexicon", lambda: {})

    ctx = PipelineContext(
        document_id=uuid4(),
        minio_key="minio://kg-documents/uploads/20260515/demo.docx",
        report_id_hint="RPT-001",
        raw_text="[SEC:D1]\n第一段内容\n\n[SEC:D2]\n第二段内容",
    )

    out = await split_run(ctx)

    assert len(out.chunks) == 1
    chunk = out.chunks[0]
    assert chunk.report_id == "RPT-001"
    assert chunk.para_idx == 0
    assert chunk.section_path == ["全文"]
    assert "[SEC:D1]" in chunk.text
    assert "第二段内容" in chunk.text
