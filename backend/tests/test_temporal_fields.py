"""temporal 字段兼容与规范化测试。"""

from datetime import datetime

from app.schemas.entity import ActionItem, EightDReport, ProductEvent, ProductInstance


def test_product_event_accepts_legacy_event_time_alias() -> None:
    event = ProductEvent.model_validate(
        {
            "business_key": "EVT-1",
            "event_id": "EVT-1",
            "event_time": "2026-04-10T00:00:00Z",
        }
    )

    assert event.occurred_at == datetime.fromisoformat("2026-04-10T00:00:00+00:00")
    dumped = event.model_dump(mode="json", exclude_none=True)
    assert dumped["occurred_at"] == "2026-04-10T00:00:00Z"
    assert "event_time" not in dumped


def test_temporal_business_fields_parse_iso_datetime() -> None:
    report = EightDReport(
        business_key="FS-1",
        report_no="FS-1",
        issue_title="issue",
        report_date="2026-04-10T00:00:00Z",
        closed_at="2026-04-25T17:00:00Z",
    )
    action = ActionItem(
        business_key="ACT-1",
        action_id="ACT-1",
        due_date="2026-04-12T08:30:00Z",
        completed_at="2026-04-11T18:45:00Z",
    )
    product = ProductInstance(
        business_key="SN-1",
        serial_number="SN-1",
        commission_date="2025-01-02T00:00:00Z",
    )

    assert report.report_date == datetime.fromisoformat("2026-04-10T00:00:00+00:00")
    assert report.closed_at == datetime.fromisoformat("2026-04-25T17:00:00+00:00")
    assert action.due_date == datetime.fromisoformat("2026-04-12T08:30:00+00:00")
    assert action.completed_at == datetime.fromisoformat("2026-04-11T18:45:00+00:00")
    assert product.commission_date == datetime.fromisoformat("2025-01-02T00:00:00+00:00")
