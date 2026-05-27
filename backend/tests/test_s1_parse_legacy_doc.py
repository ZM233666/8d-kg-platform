"""s1_parse 对 legacy .doc 文本兜底路径测试。"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from app.pipeline.context import PipelineContext
from app.pipeline.s1_parse import run

_FIXTURE_DIR = Path(__file__).resolve().parents[2] / "docs_for_test"

_LEGACY_DOC = _FIXTURE_DIR / "8D _郑州3号线TBU安装螺栓断裂调查报告_V0.0.doc"


@pytest.mark.skipif(
    not _LEGACY_DOC.exists(), reason="docs_for_test not available in this environment"
)
async def test_s1_parse_can_fallback_for_real_legacy_doc_sample() -> None:
    source = _LEGACY_DOC
    ctx = PipelineContext(
        document_id=uuid4(),
        minio_key=f"local://{source.resolve()}",
    )

    result = await run(ctx)

    assert result.raw_text
    assert "郑州3号线TBU安装螺栓断裂调查报告" in result.raw_text
    assert "根本原因分析" in result.raw_text
    assert result.raw_tables == []
    assert result.raw_images == []
