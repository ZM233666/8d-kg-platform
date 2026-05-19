"""structured_query 构造测试。"""

from app.services.query_service import _build_structured_query


def test_build_structured_query_for_report_date_filters() -> None:
    count_query, items_query, params = _build_structured_query(
        entity_type="EightDReport",
        filters={
            "report_date_from": "2026-01-01T00:00:00Z",
            "report_date_to": "2026-12-31T23:59:59Z",
            "closed_at_from": "2026-04-20T00:00:00Z",
            "closed_at_to": "2026-04-30T23:59:59Z",
            "report_status": "closed",
        },
        page=2,
        page_size=10,
        sort_by="closed_at",
        sort_order="desc",
    )

    assert "datetime(n.report_date) >= datetime($report_date_from)" in count_query
    assert "datetime(n.report_date) <= datetime($report_date_to)" in count_query
    assert "datetime(n.closed_at) >= datetime($closed_at_from)" in count_query
    assert "datetime(n.closed_at) <= datetime($closed_at_to)" in count_query
    assert "n.report_status = $report_status" in count_query
    assert "ORDER BY n.closed_at DESC" in items_query
    assert params["skip"] == 10
    assert params["limit"] == 10
    assert params["report_status"] == "closed"


def test_build_structured_query_for_occurred_at_filters() -> None:
    count_query, items_query, params = _build_structured_query(
        entity_type="ProductEvent",
        filters={
            "occurred_at_from": "2026-04-01T00:00:00Z",
            "occurred_at_to": "2026-04-30T23:59:59Z",
            "event_type": "出厂测试故障",
            "severity": "高",
        },
        page=1,
        page_size=20,
        sort_by="occurred_at",
        sort_order="asc",
    )

    assert "datetime(n.occurred_at) >= datetime($occurred_at_from)" in count_query
    assert "datetime(n.occurred_at) <= datetime($occurred_at_to)" in count_query
    assert "n.event_type = $event_type" in count_query
    assert "n.severity = $severity" in count_query
    assert "ORDER BY n.occurred_at ASC" in items_query
    assert params["skip"] == 0
    assert params["limit"] == 20


def test_build_structured_query_for_action_completed_at_filters() -> None:
    count_query, items_query, params = _build_structured_query(
        entity_type="ActionItem",
        filters={
            "completed_at_from": "2026-04-01T00:00:00Z",
            "completed_at_to": "2026-04-30T23:59:59Z",
            "action_status": "完成",
            "action_type": "纠正D5",
        },
        page=1,
        page_size=20,
        sort_by="completed_at",
        sort_order="desc",
    )

    assert "datetime(n.completed_at) >= datetime($completed_at_from)" in count_query
    assert "datetime(n.completed_at) <= datetime($completed_at_to)" in count_query
    assert "n.status = $action_status" in count_query
    assert "n.action_type = $action_type" in count_query
    assert "ORDER BY n.completed_at DESC" in items_query
    assert params["skip"] == 0
    assert params["limit"] == 20
