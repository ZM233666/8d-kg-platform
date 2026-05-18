"""从抽取结果补全/推断图谱关系（LLM 常漏填 relationships 或字段名不一致）。"""
from __future__ import annotations

import re

from app.graph.client import ALLOWED_REL_TYPES
from app.schemas.extraction import ExtractionResult, RelationTriple

_INVALID_REPORT_KEYS = frozenset({"", "UNKNOWN", "unknown", "N/A", "null", "None"})
_REPORT_ID_TEXT_RE = re.compile(
    r"(?:FS|8D|RPT)[-_]?[A-Z0-9][A-Z0-9\-_/]{3,}",
    re.IGNORECASE,
)

# LLM 偶发字段名 → 标准字段名
_REL_FIELD_ALIASES: dict[str, str] = {
    "source_label": "from_label",
    "src_label": "from_label",
    "start_label": "from_label",
    "source_key": "from_key",
    "source_bk": "from_key",
    "src_key": "from_key",
    "start_key": "from_key",
    "start_bk": "from_key",
    "target_label": "to_label",
    "dst_label": "to_label",
    "end_label": "to_label",
    "target_key": "to_key",
    "target_bk": "to_key",
    "dst_key": "to_key",
    "end_key": "to_key",
    "end_bk": "to_key",
    "relation_type": "rel_type",
    "relationship_type": "rel_type",
    "type": "rel_type",
    "rel": "rel_type",
}

# 常见非法 rel_type → 白名单映射
_REL_TYPE_ALIASES: dict[str, str] = {
    "CONTAINMENT_ACTION": "CORRECTIVE_ACTION",
    "INTERMEDIATE_CAUSE": "ROOT_CAUSE",
    "DIRECT_CAUSE": "ROOT_CAUSE",
    "ADDRESSES_FAILURE_MODE": "RELATED_FAILURE_MODE",
    "INVOLVES_PRODUCT": "AFFECTED_PRODUCT",
    "INVOLVES_PART": "AFFECTED_SERIAL",
}


def normalize_relationship_item(raw: dict) -> dict | None:
    """把单条关系 dict 归一化为 RelationTriple 可解析的五字段。"""
    if not isinstance(raw, dict):
        return None
    out: dict = {}
    for k, v in raw.items():
        key = _REL_FIELD_ALIASES.get(k, k)
        if key in ("from_label", "from_key", "to_label", "to_key", "rel_type", "properties"):
            out[key] = v
    rel_type = out.get("rel_type")
    if isinstance(rel_type, str):
        upper = rel_type.strip().upper()
        out["rel_type"] = _REL_TYPE_ALIASES.get(upper, upper)
    required = ("from_label", "from_key", "to_label", "to_key", "rel_type")
    if not all(out.get(f) for f in required):
        return None
    if out["rel_type"] not in ALLOWED_REL_TYPES:
        return None
    out.setdefault("properties", {})
    return out


def normalize_relationships_raw(data: dict) -> dict:
    """就地归一化 ExtractionResult JSON 中的 relationships 数组。"""
    rels = data.get("relationships")
    if not isinstance(rels, list):
        return data
    normalized: list[dict] = []
    for item in rels:
        n = normalize_relationship_item(item) if isinstance(item, dict) else None
        if n:
            normalized.append(n)
    data["relationships"] = normalized
    return data


def resolve_report_business_key(
    er: ExtractionResult,
    report_id_hint: str | None = None,
) -> str | None:
    """解析 8D 报告 business_key；LLM 常输出 UNKNOWN，需从 hint / event_id 兜底。"""
    if er.report:
        for candidate in (er.report.business_key, er.report.report_no):
            if candidate and candidate.strip() not in _INVALID_REPORT_KEYS:
                return candidate.strip()
    if report_id_hint and report_id_hint.strip() not in _INVALID_REPORT_KEYS:
        return report_id_hint.strip()
    if er.event and er.event.event_id:
        eid = er.event.event_id.strip()
        if eid.startswith("EVT-"):
            return "FS-" + eid[4:]
    if er.chunks:
        for c in er.chunks[:3]:
            m = _REPORT_ID_TEXT_RE.search(c.text or "")
            if m:
                return m.group(0).upper().replace("_", "-")
    return None


def _sync_entity_business_keys(
    er: ExtractionResult,
    report_id_hint: str | None = None,
) -> None:
    """让 business_key 与 report_no / event_id 等主字段一致，避免关系端点找不到节点。"""
    resolved_report = resolve_report_business_key(er, report_id_hint)
    if er.report and resolved_report:
        er.report.business_key = resolved_report
        er.report.report_no = resolved_report
    if er.event and er.event.event_id:
        er.event.business_key = er.event.event_id
    for fm in er.failure_modes:
        if fm.mode_code:
            fm.business_key = fm.mode_code
    for cause in er.causes:
        if cause.cause_id:
            cause.business_key = cause.cause_id
    for action in er.actions:
        if action.action_id:
            action.business_key = action.action_id
    for pi in er.product_instances:
        if pi.serial_number:
            pi.business_key = pi.serial_number
    for ps in er.part_serials:
        if ps.part_key:
            ps.business_key = ps.part_key
    for org in er.organizations:
        if org.org_code:
            org.business_key = org.org_code


def _action_rel_type(action_type: str | None) -> str:
    if action_type and any(x in action_type for x in ("预防", "D7", "防再发")):
        return "PREVENTIVE_ACTION"
    return "CORRECTIVE_ACTION"


def infer_relationships(er: ExtractionResult) -> list[RelationTriple]:
    """根据已抽取实体推断主线 8D 关系（LLM 未输出 relationships 时兜底）。"""
    rels: list[RelationTriple] = []
    report_bk = er.report.business_key if er.report else None
    event_bk = er.event.business_key if er.event else None

    if event_bk and report_bk:
        rels.append(
            RelationTriple(
                from_label="ProductEvent",
                from_key=event_bk,
                to_label="EightDReport",
                to_key=report_bk,
                rel_type="HAS_8D_REPORT",
            )
        )

    if report_bk:
        for cause in er.causes:
            rels.append(
                RelationTriple(
                    from_label="EightDReport",
                    from_key=report_bk,
                    to_label="CauseItem",
                    to_key=cause.business_key,
                    rel_type="ROOT_CAUSE",
                )
            )
        for action in er.actions:
            rels.append(
                RelationTriple(
                    from_label="EightDReport",
                    from_key=report_bk,
                    to_label="ActionItem",
                    to_key=action.business_key,
                    rel_type=_action_rel_type(action.action_type),
                )
            )
        for org in er.organizations:
            rels.append(
                RelationTriple(
                    from_label="EightDReport",
                    from_key=report_bk,
                    to_label="Organization",
                    to_key=org.business_key,
                    rel_type="RESPONSIBLE_ORG",
                )
            )
        for pi in er.product_instances:
            rels.append(
                RelationTriple(
                    from_label="EightDReport",
                    from_key=report_bk,
                    to_label="ProductInstance",
                    to_key=pi.business_key,
                    rel_type="AFFECTED_PRODUCT",
                )
            )
        for ps in er.part_serials:
            rels.append(
                RelationTriple(
                    from_label="EightDReport",
                    from_key=report_bk,
                    to_label="PartSerial",
                    to_key=ps.business_key,
                    rel_type="AFFECTED_SERIAL",
                )
            )

    if event_bk:
        for fm in er.failure_modes:
            rels.append(
                RelationTriple(
                    from_label="ProductEvent",
                    from_key=event_bk,
                    to_label="FailureMode",
                    to_key=fm.business_key,
                    rel_type="RELATED_FAILURE_MODE",
                )
            )
        for pi in er.product_instances:
            rels.append(
                RelationTriple(
                    from_label="ProductEvent",
                    from_key=event_bk,
                    to_label="ProductInstance",
                    to_key=pi.business_key,
                    rel_type="HAPPENED_ON",
                )
            )
        for ps in er.part_serials:
            rels.append(
                RelationTriple(
                    from_label="ProductEvent",
                    from_key=event_bk,
                    to_label="PartSerial",
                    to_key=ps.business_key,
                    rel_type="RELATED_SERIAL",
                )
            )

    for cause in er.causes:
        for fm in er.failure_modes:
            rels.append(
                RelationTriple(
                    from_label="CauseItem",
                    from_key=cause.business_key,
                    to_label="FailureMode",
                    to_key=fm.business_key,
                    rel_type="RELATED_FAILURE_MODE",
                )
            )

    for ps in er.part_serials:
        for org in er.organizations:
            rels.append(
                RelationTriple(
                    from_label="PartSerial",
                    from_key=ps.business_key,
                    to_label="Organization",
                    to_key=org.business_key,
                    rel_type="SUPPLIED_BY",
                )
            )
        for pi in er.product_instances:
            rels.append(
                RelationTriple(
                    from_label="PartSerial",
                    from_key=ps.business_key,
                    to_label="ProductInstance",
                    to_key=pi.business_key,
                    rel_type="INSTALLED_ON",
                )
            )

    # 措施验证根因：仅对已验证原因建边，避免 action×cause 全连接噪声
    verified_causes = [c for c in er.causes if c.is_verified]
    if verified_causes:
        for action in er.actions:
            for cause in verified_causes:
                rels.append(
                    RelationTriple(
                        from_label="ActionItem",
                        from_key=action.business_key,
                        to_label="CauseItem",
                        to_key=cause.business_key,
                        rel_type="VERIFIES_CAUSE",
                    )
                )

    return rels


def _rel_key(r: RelationTriple) -> tuple[str, str, str, str, str]:
    return (r.from_label, r.from_key, r.rel_type, r.to_label, r.to_key)


def merge_relationships(
    explicit: list[RelationTriple],
    inferred: list[RelationTriple],
) -> list[RelationTriple]:
    """显式关系优先，推断关系补缺。"""
    seen: set[tuple[str, str, str, str, str]] = set()
    out: list[RelationTriple] = []
    for r in explicit + inferred:
        key = _rel_key(r)
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def enrich_extraction_result(
    er: ExtractionResult,
    *,
    report_id_hint: str | None = None,
) -> ExtractionResult:
    """同步 business_key、合并推断关系，保证入图时边不缺失。"""
    _sync_entity_business_keys(er, report_id_hint=report_id_hint)
    inferred = infer_relationships(er)
    er.relationships = merge_relationships(er.relationships, inferred)
    return er
