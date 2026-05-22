"""面向 Codex structured output 的精简 JSON Schema。"""

from __future__ import annotations

from typing import Any


def build_codex_output_schema(
    response_model_name: str, fallback_schema: dict[str, Any]
) -> dict[str, Any]:
    """为特定响应模型返回更适合 Codex 的 strict schema。"""
    if response_model_name == "ExtractionResult":
        return _build_extraction_result_schema()
    return fallback_schema


def _nullable(schema: dict[str, Any]) -> dict[str, Any]:
    return {"anyOf": [schema, {"type": "null"}]}


def _string() -> dict[str, Any]:
    return {"type": "string"}


def _number() -> dict[str, Any]:
    return {"type": "number"}


def _boolean() -> dict[str, Any]:
    return {"type": "boolean"}


def _array(items: dict[str, Any]) -> dict[str, Any]:
    return {"type": "array", "items": items}


def _strict_object(properties: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties.keys()),
        "additionalProperties": False,
    }


def _build_extraction_result_schema() -> dict[str, Any]:
    report = _strict_object(
        {
            "business_key": _string(),
            "report_no": _string(),
            "issue_title": _nullable(_string()),
            "report_date": _nullable(_string()),
            "closed_at": _nullable(_string()),
            "report_status": _nullable(_string()),
            "d2_problem_statement": _nullable(_string()),
            "d4_root_cause_summary": _nullable(_string()),
            "d5_permanent_correction_summary": _nullable(_string()),
            "d7_prevention_summary": _nullable(_string()),
            "owner_name": _nullable(_string()),
            "owner_role": _nullable(_string()),
            "supporting_chunks": _array(_string()),
        }
    )
    event = _strict_object(
        {
            "business_key": _string(),
            "event_id": _string(),
            "event_code": _nullable(_string()),
            "event_type": _nullable(_string()),
            "severity": _nullable(_string()),
            "symptom": _nullable(_string()),
            "occurred_at": _nullable(_string()),
            "status": _nullable(_string()),
            "reporter_name": _nullable(_string()),
            "supporting_chunks": _array(_string()),
        }
    )
    failure_mode = _strict_object(
        {
            "business_key": _string(),
            "mode_code": _string(),
            "mode_name": _nullable(_string()),
            "category": _nullable(_string()),
            "supporting_chunks": _array(_string()),
        }
    )
    cause = _strict_object(
        {
            "business_key": _string(),
            "cause_id": _string(),
            "title": _nullable(_string()),
            "cause_type": _nullable(_string()),
            "is_verified": _nullable(_boolean()),
            "evidence": _nullable(_string()),
            "supporting_chunks": _array(_string()),
        }
    )
    action = _strict_object(
        {
            "business_key": _string(),
            "action_id": _string(),
            "title": _nullable(_string()),
            "action_type": _nullable(_string()),
            "status": _nullable(_string()),
            "owner_name": _nullable(_string()),
            "due_date": _nullable(_string()),
            "completed_at": _nullable(_string()),
            "supporting_chunks": _array(_string()),
        }
    )
    product_instance = _strict_object(
        {
            "business_key": _string(),
            "serial_number": _string(),
            "asset_code": _nullable(_string()),
            "commission_date": _nullable(_string()),
            "status": _nullable(_string()),
            "owner_name": _nullable(_string()),
            "site_city": _nullable(_string()),
            "site_country": _nullable(_string()),
            "site_code": _nullable(_string()),
            "supporting_chunks": _array(_string()),
        }
    )
    part_serial = _strict_object(
        {
            "business_key": _string(),
            "part_key": _string(),
            "serial_number": _nullable(_string()),
            "batch_no": _nullable(_string()),
            "status": _nullable(_string()),
            "supplier_name": _nullable(_string()),
            "supporting_chunks": _array(_string()),
        }
    )
    organization = _strict_object(
        {
            "business_key": _string(),
            "org_code": _string(),
            "org_name": _nullable(_string()),
            "org_type": _nullable(_string()),
            "supporting_chunks": _array(_string()),
        }
    )
    person = _strict_object(
        {
            "business_key": _string(),
            "person_id": _string(),
            "person_name": _nullable(_string()),
            "title": _nullable(_string()),
            "department": _nullable(_string()),
            "email": _nullable(_string()),
            "supporting_chunks": _array(_string()),
        }
    )
    relation = _strict_object(
        {
            "from_label": _string(),
            "from_key": _string(),
            "to_label": _string(),
            "to_key": _string(),
            "rel_type": _string(),
            "properties": _strict_object({}),
        }
    )
    return _strict_object(
        {
            "report": _nullable(report),
            "event": _nullable(event),
            "failure_modes": _array(failure_mode),
            "causes": _array(cause),
            "actions": _array(action),
            "product_instances": _array(product_instance),
            "part_serials": _array(part_serial),
            "organizations": _array(organization),
            "persons": _array(person),
            "relationships": _array(relation),
            "chunks": _array(_strict_object({})),
            "stats": _strict_object({}),
        }
    )
