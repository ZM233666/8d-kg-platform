"""Codex regression fixture 资产校验。"""

from __future__ import annotations

import json
from pathlib import Path

from app.pipeline.context import PipelineContext
from app.schemas.extraction import ExtractionResult

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "codex_regression"


def test_codex_regression_fixtures_have_required_shape() -> None:
    fixture_paths = sorted(FIXTURE_DIR.glob("*.json"))

    assert fixture_paths, "codex regression fixture directory should not be empty"

    seen_names: set[str] = set()
    for path in fixture_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))

        assert payload.get("name"), f"{path.name} missing fixture name"
        assert payload["name"] not in seen_names, f"duplicated fixture name: {payload['name']}"
        seen_names.add(payload["name"])

        assert "context" in payload, f"{path.name} missing context"
        assert "llm_result" in payload, f"{path.name} missing llm_result"
        if "source_document" in payload:
            source_path = Path(payload["source_document"])
            if not source_path.exists():
                import pytest

                pytest.skip(f"{path.name} source document not available in this environment: {source_path}")

        ctx = PipelineContext.model_validate(
            {
                **payload["context"],
                "document_id": "00000000-0000-0000-0000-000000000001",
            }
        )
        result = ExtractionResult.model_validate(payload["llm_result"])

        assert ctx.chunks, f"{path.name} should contain at least one chunk"
        assert result.report is not None, f"{path.name} should contain a report payload"
