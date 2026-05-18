"""relationship_builder 单元测试。"""
from app.pipeline.relationship_builder import (
    enrich_extraction_result,
    infer_relationships,
    merge_relationships,
    normalize_relationship_item,
    resolve_report_business_key,
)
from app.schemas.entity import (
    ActionItem,
    CauseItem,
    EightDReport,
    FailureMode,
    ProductEvent,
)
from app.schemas.extraction import ExtractionResult, RelationTriple


def test_normalize_relationship_aliases():
    raw = {
        "source_label": "ProductEvent",
        "source_key": "EVT-1",
        "target_label": "EightDReport",
        "target_key": "RPT-1",
        "relation_type": "HAS_8D_REPORT",
    }
    n = normalize_relationship_item(raw)
    assert n is not None
    assert n["from_key"] == "EVT-1"
    assert n["rel_type"] == "HAS_8D_REPORT"


def test_infer_report_event_and_cause():
    er = ExtractionResult(
        report=EightDReport(business_key="R1", report_no="R1", issue_title="t"),
        event=ProductEvent(business_key="E1", event_id="E1"),
        causes=[CauseItem(business_key="C1", cause_id="C1", title="root")],
        actions=[ActionItem(business_key="A1", action_id="A1", title="fix", action_type="纠正D5")],
        failure_modes=[FailureMode(business_key="FM1", mode_code="FM1")],
    )
    inferred = infer_relationships(er)
    types = {r.rel_type for r in inferred}
    assert "HAS_8D_REPORT" in types
    assert "ROOT_CAUSE" in types
    assert "CORRECTIVE_ACTION" in types
    assert "RELATED_FAILURE_MODE" in types


def test_resolve_report_from_event_when_unknown():
    er = ExtractionResult(
        report=EightDReport(business_key="UNKNOWN", report_no="UNKNOWN", issue_title="t"),
        event=ProductEvent(business_key="EVT-EP2002-2022-001", event_id="EVT-EP2002-2022-001"),
    )
    assert resolve_report_business_key(er) == "FS-EP2002-2022-001"


def test_enrich_syncs_report_key_and_merges():
    er = ExtractionResult(
        report=EightDReport(business_key="UNKNOWN", report_no="FS-001", issue_title="t"),
        event=ProductEvent(business_key="EVT-FS-001", event_id="EVT-FS-001"),
        relationships=[
            RelationTriple(
                from_label="ProductEvent",
                from_key="EVT-FS-001",
                to_label="EightDReport",
                to_key="FS-001",
                rel_type="HAS_8D_REPORT",
            )
        ],
    )
    enrich_extraction_result(er, report_id_hint="FS-001")
    assert er.report is not None
    assert er.report.business_key == "FS-001"
    assert any(r.rel_type == "HAS_8D_REPORT" for r in er.relationships)


def test_merge_explicit_over_inferred():
    explicit = [
        RelationTriple(
            from_label="ProductEvent",
            from_key="E",
            to_label="EightDReport",
            to_key="R",
            rel_type="HAS_8D_REPORT",
        )
    ]
    inferred = list(explicit)
    merged = merge_relationships(explicit, inferred)
    assert len(merged) == 1
