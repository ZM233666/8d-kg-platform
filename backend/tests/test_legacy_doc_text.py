"""旧版 .doc 文本兜底解析测试。"""

from __future__ import annotations

from pathlib import Path

import pytest
from app.services.legacy_doc_text import extract_text_from_legacy_doc

_FIXTURE_DIR = Path(__file__).resolve().parents[2] / "docs_for_test"

_LEGACY_DOC = _FIXTURE_DIR / "8D _郑州3号线TBU安装螺栓断裂调查报告_V0.0.doc"


@pytest.mark.skipif(not _LEGACY_DOC.exists(), reason="docs_for_test not available in this environment")
def test_extract_text_from_legacy_doc_returns_readable_text_for_real_sample() -> None:
    source = _LEGACY_DOC

    text = extract_text_from_legacy_doc(source)

    assert "郑州3号线TBU安装螺栓断裂调查报告" in text
    assert "问题描述" in text
    assert "根本原因分析" in text
    assert "2020/11/20四方厂内班组人员在组装郑州3号线T22列车TBU时" in text
