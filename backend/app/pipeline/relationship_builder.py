"""从抽取结果补全或推断图谱关系 (LLM 常漏填 relationships 或字段名不一致)."""

from __future__ import annotations

import re

from app.graph.client import ALLOWED_LABELS, ALLOWED_REL_TYPES
from app.lexicon import load_lexicon
from app.schemas.entity import FailureProduct, FailureProductMention, Organization, Person
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
    "AFFECTED_INSTANCE": "AFFECTED_PRODUCT",
    "TARGET_INSTANCE": "TARGET_PRODUCT",
    "RESPONSIBLE_DEPARTMENT": "RESPONSIBLE_ORG",
    "RESPONSIBLE_DEPT": "RESPONSIBLE_ORG",
    "VALIDATES_CAUSE": "VERIFIES_CAUSE",
    "VERIFIED_CAUSE": "VERIFIES_CAUSE",
}

_BUSINESS_LABELS = frozenset(ALLOWED_LABELS - {"Chunk"})
_REL_ENDPOINT_RULES: dict[str, frozenset[tuple[str, str]]] = {
    "HAS_8D_REPORT": frozenset({("ProductEvent", "EightDReport")}),
    "RELATED_FAILURE_MODE": frozenset(
        {
            ("ProductEvent", "FailureMode"),
            ("CauseItem", "FailureMode"),
        }
    ),
    "ROOT_CAUSE": frozenset({("EightDReport", "CauseItem")}),
    "CORRECTIVE_ACTION": frozenset({("EightDReport", "ActionItem")}),
    "PREVENTIVE_ACTION": frozenset({("EightDReport", "ActionItem")}),
    "VERIFIES_CAUSE": frozenset({("ActionItem", "CauseItem")}),
    "HAPPENED_ON": frozenset({("ProductEvent", "ProductInstance")}),
    "RELATED_SERIAL": frozenset({("ProductEvent", "PartSerial")}),
    "AFFECTED_PRODUCT": frozenset({("EightDReport", "ProductInstance")}),
    "AFFECTED_SERIAL": frozenset({("EightDReport", "PartSerial")}),
    "RESPONSIBLE_ORG": frozenset(
        {
            ("EightDReport", "Organization"),
            ("ActionItem", "Organization"),
        }
    ),
    "INVOLVES_PERSON": frozenset({("EightDReport", "Person")}),
    "AUTHORED_BY_PERSON": frozenset({("EightDReport", "Person")}),
    "REVIEWED_BY_PERSON": frozenset({("EightDReport", "Person")}),
    "REPORTED_BY_PERSON": frozenset({("ProductEvent", "Person")}),
    "OWNED_BY_PERSON": frozenset(
        {
            ("EightDReport", "Person"),
            ("ActionItem", "Person"),
        }
    ),
    "TARGET_SERIAL": frozenset({("ActionItem", "PartSerial")}),
    "TARGET_PRODUCT": frozenset({("ActionItem", "ProductInstance")}),
    "INSTALLED_ON": frozenset({("PartSerial", "ProductInstance")}),
    "SUPPLIED_BY": frozenset({("PartSerial", "Organization")}),
    "MENTIONED_IN": frozenset((label, "Chunk") for label in _BUSINESS_LABELS),
    "MENTIONS": frozenset(("Chunk", label) for label in _BUSINESS_LABELS),
    "MENTIONS_FAILURE_PRODUCT": frozenset({("EightDReport", "FailureProductMention")}),
    "INSTANCE_OF_FAILURE_PRODUCT": frozenset({("FailureProductMention", "FailureProduct")}),
}
_COMPANY_MARKERS = (
    "有限公司",
    "公司",
    "co., ltd",
    "co.,ltd",
    " ltd",
    "inc",
    "corp",
    "corporation",
    "gmbh",
)
_DEPARTMENT_MARKERS = ("部门", "项目组", "小组", "中心", "team", "department", "quality", "制造部")
_OPERATOR_MARKERS = (
    "运营商",
    "operator",
    "地铁",
    "深铁",
    "轨道交通",
    "铁路局",
    "metro",
)
_OPERATOR_NAME_RE = re.compile(
    r"[\u4e00-\u9fffA-Za-z0-9]{2,20}(?:地铁|深铁|轨道交通|铁路局)",
)
_OPERATOR_NOISE_TOKENS = (
    "该型号",
    "螺栓",
    "故障",
    "调查",
    "报告",
    "断裂",
    "运用于",
    "用于",
    "进行",
    "分析",
)
_GENERIC_ORG_NAMES = frozenset(
    {
        "供应商",
        "客户",
        "部门",
        "项目组",
        "小组",
        "团队",
        "内部部门",
        "supplier",
        "customer",
        "department",
        "team",
    }
)
_GENERIC_SUPPLIER_NAMES = frozenset({"供应商", "supplier"})
_OWNER_SIGNAL_RE = re.compile(
    r"(负责人|责任人|owner|报告人|负责人姓名|责任部门|责任单位)", re.IGNORECASE
)
_SEVERITY_SIGNAL_RE = re.compile(r"(等级|级别|severity|定义为|分类为|风险等级)", re.IGNORECASE)
_PERSON_TITLE_RE = re.compile(r"(工|经理|主任|总监|总工|班长|老师|工程师)$")
_PERSON_CONTEXT_SIGNAL_RE = re.compile(
    r"(负责人|责任人|联系人|报告人|上报人|owner|operator|操作人|责任工程师|责任经理)",
    re.IGNORECASE,
)
_AMOUNT_RE = re.compile(r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>pcs?|件|个)?", re.IGNORECASE)
_FAMILY_TOKEN_RE = re.compile(r"([A-Za-z]{1,8}\d{2,}[A-Za-z0-9-]*)")


def _is_valid_relation_endpoint(*, rel_type: str, from_label: str, to_label: str) -> bool:
    allowed_pairs = _REL_ENDPOINT_RULES.get(rel_type)
    if not allowed_pairs:
        return False
    return (from_label, to_label) in allowed_pairs


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
    for label_key in ("from_label", "to_label"):
        label_value = out.get(label_key)
        if isinstance(label_value, str):
            out[label_key] = label_value.strip()
    required = ("from_label", "from_key", "to_label", "to_key", "rel_type")
    if not all(out.get(f) for f in required):
        return None
    if out["from_label"] not in ALLOWED_LABELS or out["to_label"] not in ALLOWED_LABELS:
        return None
    if out["rel_type"] not in ALLOWED_REL_TYPES:
        return None
    if not _is_valid_relation_endpoint(
        rel_type=out["rel_type"],
        from_label=out["from_label"],
        to_label=out["to_label"],
    ):
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


def filter_supported_relationships(
    relationships: list[RelationTriple],
) -> list[RelationTriple]:
    """过滤 runtime 不支持的显式关系端点组合。"""
    filtered: list[RelationTriple] = []
    for relation in relationships:
        normalized = normalize_relationship_item(relation.model_dump(mode="json"))
        if not normalized:
            continue
        filtered.append(RelationTriple.model_validate(normalized))
    return filtered


def resolve_report_business_key(
    er: ExtractionResult,
    report_id_hint: str | None = None,
) -> str | None:
    """解析 8D 报告 business_key, LLM 常输出 UNKNOWN, 需从 hint / event_id 兜底."""

    def _is_invalid_report_key(candidate: str | None) -> bool:
        if not candidate:
            return True
        stripped = candidate.strip()
        if stripped in _INVALID_REPORT_KEYS:
            return True
        normalized = _normalize_match_text(stripped)
        return "unknown" in normalized

    if er.report:
        for candidate in (er.report.business_key, er.report.report_no):
            if not _is_invalid_report_key(candidate):
                return candidate.strip()
    if not _is_invalid_report_key(report_id_hint):
        return report_id_hint.strip()
    if er.event and er.event.event_id:
        eid = er.event.event_id.strip()
        if eid.startswith("EVT-") and not _is_invalid_report_key(eid):
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
) -> dict[str, dict[str, str]]:
    """让 business_key 与 report_no / event_id 等主字段一致, 避免关系端点找不到节点."""
    key_mapping: dict[str, dict[str, str]] = {}

    def _record_mapping(label: str, old_key: str | None, new_key: str | None) -> None:
        if not old_key or not new_key or old_key == new_key:
            return
        label_map = key_mapping.setdefault(label, {})
        label_map[old_key] = new_key

    resolved_report = resolve_report_business_key(er, report_id_hint)
    if er.report and resolved_report:
        old_report_key = er.report.business_key
        er.report.business_key = resolved_report
        er.report.report_no = resolved_report
        _record_mapping("EightDReport", old_report_key, er.report.business_key)
    if er.event and er.event.event_id:
        old_event_key = er.event.business_key
        er.event.business_key = er.event.event_id
        _record_mapping("ProductEvent", old_event_key, er.event.business_key)
    for fm in er.failure_modes:
        if fm.mode_code:
            old_key = fm.business_key
            fm.business_key = fm.mode_code
            _record_mapping("FailureMode", old_key, fm.business_key)
    for cause in er.causes:
        if cause.cause_id:
            old_key = cause.business_key
            cause.business_key = cause.cause_id
            _record_mapping("CauseItem", old_key, cause.business_key)
    for action in er.actions:
        if action.action_id:
            old_key = action.business_key
            action.business_key = action.action_id
            _record_mapping("ActionItem", old_key, action.business_key)
    for pi in er.product_instances:
        if pi.serial_number:
            old_key = pi.business_key
            pi.business_key = pi.serial_number
            _record_mapping("ProductInstance", old_key, pi.business_key)
    for ps in er.part_serials:
        if ps.part_key:
            old_key = ps.business_key
            ps.business_key = ps.part_key
            _record_mapping("PartSerial", old_key, ps.business_key)
    for org in er.organizations:
        if org.org_code:
            old_key = org.business_key
            org.business_key = org.org_code
            _record_mapping("Organization", old_key, org.business_key)
    for person in er.persons:
        if person.person_id:
            old_key = person.business_key
            person.business_key = person.person_id
            _record_mapping("Person", old_key, person.business_key)
    for product in er.failure_products:
        if product.business_key:
            old_key = product.business_key
            canonical_key = _build_failure_product_key(
                kb_part_name=product.KBPartName or product.canonical_name,
                kb_part_number=product.KBPartNumber,
            )
            product.business_key = canonical_key
            _record_mapping("FailureProduct", old_key, product.business_key)
    for index, mention in enumerate(er.failure_product_mentions):
        old_key = mention.business_key
        report_scope = (
            mention.report_no
            or resolved_report
            or (report_id_hint.strip() if report_id_hint else None)
            or "UNKNOWN"
        )
        if not mention.business_key or mention.business_key.startswith("UNKNOWN"):
            mention.business_key = _build_failure_product_mention_key(
                report_scope=report_scope,
                kb_part_name=mention.KBPartName,
                kb_part_number=mention.KBPartNumber,
                amount=mention.Amount,
                index=index,
            )
        _record_mapping("FailureProductMention", old_key, mention.business_key)
        if mention.failure_product_key:
            mention.failure_product_key = _build_failure_product_key(
                kb_part_name=mention.KBPartName,
                kb_part_number=mention.KBPartNumber,
            )
    return key_mapping


def _sync_relationship_endpoint_keys(
    er: ExtractionResult,
    key_mapping: dict[str, dict[str, str]],
) -> None:
    """当实体 business_key 被归一后，同步修正显式 relationships 的端点 key。"""
    if not key_mapping:
        return
    for relation in er.relationships:
        from_map = key_mapping.get(relation.from_label)
        if from_map:
            relation.from_key = from_map.get(relation.from_key, relation.from_key)
        to_map = key_mapping.get(relation.to_label)
        if to_map:
            relation.to_key = to_map.get(relation.to_key, relation.to_key)


def _sync_chunk_business_keys(
    er: ExtractionResult,
    report_id_hint: str | None = None,
) -> None:
    """让 chunk/report/supporting_chunks 的 report scope 保持一致。"""
    if not er.chunks:
        return

    resolved_report = resolve_report_business_key(er, report_id_hint)
    if not resolved_report:
        return

    chunk_key_mapping: dict[str, str] = {}
    for chunk in er.chunks:
        old_chunk_id = chunk.chunk_id
        if "#" in old_chunk_id:
            suffix = old_chunk_id.split("#", 1)[1]
        else:
            suffix = f"full_document#{chunk.para_idx}"
        new_chunk_id = f"{resolved_report}#{suffix}"
        chunk.report_id = resolved_report
        chunk.chunk_id = new_chunk_id
        if old_chunk_id != new_chunk_id:
            chunk_key_mapping[old_chunk_id] = new_chunk_id

    if not chunk_key_mapping:
        return

    def _rewrite_supporting_chunks(entity) -> None:
        supporting_chunks = getattr(entity, "supporting_chunks", None)
        if supporting_chunks is None:
            return
        entity.supporting_chunks = [
            chunk_key_mapping.get(chunk_id, chunk_id) for chunk_id in supporting_chunks
        ]

    entities = [
        er.report,
        er.event,
        *er.failure_modes,
        *er.causes,
        *er.actions,
        *er.product_instances,
        *er.part_serials,
        *er.organizations,
        *er.persons,
        *er.failure_products,
        *er.failure_product_mentions,
    ]
    for entity in entities:
        if entity is None:
            continue
        _rewrite_supporting_chunks(entity)

    for relation in er.relationships:
        if relation.from_label == "Chunk":
            relation.from_key = chunk_key_mapping.get(relation.from_key, relation.from_key)
        if relation.to_label == "Chunk":
            relation.to_key = chunk_key_mapping.get(relation.to_key, relation.to_key)


def _action_rel_type(action_type: str | None) -> str:
    if action_type and any(x in action_type for x in ("预防", "D7", "防再发")):
        return "PREVENTIVE_ACTION"
    return "CORRECTIVE_ACTION"


def _single_or_none(items: list):
    return items[0] if len(items) == 1 else None


def _org_type_text(org) -> str:
    return ((org.org_type or "") + " " + (org.org_name or "")).strip().lower()


def _looks_like_supplier(org) -> bool:
    text = _org_type_text(org)
    return any(token in text for token in ("供应商", "supplier"))


def _looks_like_responsible_org(org) -> bool:
    text = _org_type_text(org)
    return any(
        token in text
        for token in ("部门", "项目组", "小组", "责任", "department", "team", "quality", "制造部")
    )


def _looks_like_company_name(name: str | None) -> bool:
    if not name:
        return False
    lowered = name.strip().lower()
    return any(marker in lowered for marker in _COMPANY_MARKERS)


def _looks_like_operator_name(name: str | None) -> bool:
    if not name:
        return False
    lowered = name.strip().lower()
    return any(marker in lowered for marker in _OPERATOR_MARKERS)


def _is_noisy_org_name(name: str | None) -> bool:
    if not name:
        return True
    stripped = name.strip()
    if not stripped:
        return True
    if stripped[0] in {"且", "并", "而", "及", "和", "与"}:
        return True
    if any(token in stripped for token in _OPERATOR_NOISE_TOKENS):
        return True
    if len(stripped) > 18 and "有限公司" not in stripped and "集团" not in stripped:
        return True
    if any(p in stripped for p in ("，", "。", "；", ";", ",", ".", "：", ":")):
        return True
    return False


def _is_generic_supplier_name(name: str | None) -> bool:
    if not name:
        return False
    stripped = name.strip()
    if not stripped:
        return False
    lowered = stripped.lower()
    return stripped in _GENERIC_SUPPLIER_NAMES or lowered in _GENERIC_SUPPLIER_NAMES


def _looks_like_department_name(name: str | None) -> bool:
    if not name:
        return False
    lowered = name.strip().lower()
    return any(marker in lowered for marker in _DEPARTMENT_MARKERS)


def _canonicalize_organization(org) -> None:
    lexicon = load_lexicon()
    alias_entries = lexicon.get("organization_aliases", [])
    current_values = {
        candidate
        for candidate in (
            _normalize_match_text(org.business_key),
            _normalize_match_text(org.org_code),
            _normalize_match_text(org.org_name),
        )
        if candidate
    }

    for entry in alias_entries:
        candidates = {
            candidate
            for candidate in (
                _normalize_match_text(entry.get("canonical_code")),
                _normalize_match_text(entry.get("canonical_name")),
                *[_normalize_match_text(alias) for alias in entry.get("aliases", [])],
            )
            if candidate
        }
        if not current_values.intersection(candidates):
            continue

        canonical_code = entry.get("canonical_code")
        canonical_name = entry.get("canonical_name")
        canonical_type = entry.get("org_type")
        if canonical_code:
            org.business_key = canonical_code
            org.org_code = canonical_code
        if canonical_name:
            org.org_name = canonical_name
        if canonical_type:
            org.org_type = canonical_type
        return


def normalize_organizations(er: ExtractionResult) -> dict[str, str]:
    """对 Organization 做保守归一, 减少公司或部门误判."""
    alias_map: dict[str, str] = {}
    deduped: dict[str, Organization] = {}
    ordered_keys: list[str] = []

    for org in er.organizations:
        original_values = {
            candidate
            for candidate in (
                _normalize_match_text(org.business_key),
                _normalize_match_text(org.org_code),
                _normalize_match_text(org.org_name),
            )
            if candidate
        }
        _canonicalize_organization(org)
        org_name = (org.org_name or "").strip()
        org_type = (org.org_type or "").strip()
        canonical_key = org.business_key

        if not org_name and not org_type:
            continue
        if _is_generic_supplier_name(org_name or org.business_key):
            continue
        if (
            not _find_canonical_org_entry(org.business_key)
            and not _find_canonical_org_entry(org.org_name)
            and _is_noisy_org_name(org_name or org.business_key)
        ):
            continue
        if _looks_like_supplier(org):
            org.org_type = "供应商"
        elif _looks_like_operator_name(org_name) or "运营商" in org_type:
            org.org_type = "运营商"
        elif _looks_like_department_name(org_name):
            if not org_type:
                org.org_type = "部门"
        elif _looks_like_company_name(org_name) and org_type in {"", "内部部门", "部门", "项目组"}:
            org.org_type = "公司"

        if _should_scope_org_locally(org):
            local_key = _build_local_org_business_key(er, org.org_name or org.business_key)
            org.business_key = local_key
            org.org_code = local_key
            canonical_key = local_key

        for value in original_values:
            alias_map[value] = canonical_key
        alias_map[_normalize_match_text(org.business_key)] = canonical_key
        alias_map[_normalize_match_text(org.org_code)] = canonical_key
        alias_map[_normalize_match_text(org.org_name)] = canonical_key

        existing = deduped.get(canonical_key)
        if existing is None:
            deduped[canonical_key] = org
            ordered_keys.append(canonical_key)
            continue
        _merge_organization(existing, org)

    er.organizations = [deduped[key] for key in ordered_keys]
    return alias_map


def _merge_organization(target: Organization, incoming: Organization) -> None:
    """按 canonical business_key 合并重复 Organization。"""
    target.supporting_chunks = _merge_unique_text_list(
        target.supporting_chunks + incoming.supporting_chunks
    )
    target.source_section = _merge_unique_text_list(target.source_section + incoming.source_section)

    for attr in ("org_code", "org_name", "org_type", "source_doc_id", "owner_id"):
        current = getattr(target, attr)
        candidate = getattr(incoming, attr)
        preferred = _prefer_text_value(current, candidate)
        if preferred is not None:
            setattr(target, attr, preferred)

    for attr in ("description", "summary"):
        current = getattr(target, attr)
        candidate = getattr(incoming, attr)
        preferred = _prefer_richer_text_value(current, candidate)
        if preferred is not None:
            setattr(target, attr, preferred)

    target.confidence = max(target.confidence, incoming.confidence)
    if target.created_at is None:
        target.created_at = incoming.created_at
    if target.updated_at is None or (
        incoming.updated_at is not None and incoming.updated_at > target.updated_at
    ):
        target.updated_at = incoming.updated_at


def _merge_unique_text_list(values: list[str]) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        merged.append(value)
    return merged


def _prefer_text_value(current: str | None, candidate: str | None) -> str | None:
    current_text = (current or "").strip()
    candidate_text = (candidate or "").strip()
    if not current_text:
        return candidate_text or current
    if not candidate_text:
        return current
    if len(candidate_text) > len(current_text):
        return candidate_text
    return current


def _prefer_richer_text_value(current: str | None, candidate: str | None) -> str | None:
    current_text = (current or "").strip()
    candidate_text = (candidate or "").strip()
    if not current_text:
        return candidate_text or current
    if not candidate_text:
        return current
    if len(candidate_text) > len(current_text):
        return candidate_text
    return current


def _supporting_chunk_text(er: ExtractionResult, chunk_ids: list[str]) -> str:
    text_by_chunk = {chunk.chunk_id: chunk.text for chunk in er.chunks}
    return "\n".join(
        text_by_chunk.get(chunk_id, "") for chunk_id in chunk_ids if chunk_id in text_by_chunk
    )


def _looks_like_orgish_name(name: str | None) -> bool:
    if not name:
        return False
    return (
        _looks_like_company_name(name)
        or _looks_like_operator_name(name)
        or _looks_like_department_name(name)
        or "供应商" in name
        or "客户" in name
    )


def _looks_like_generic_org_name(name: str | None) -> bool:
    if not name:
        return False
    stripped = name.strip()
    lowered = stripped.lower()
    if stripped in _GENERIC_ORG_NAMES or lowered in _GENERIC_ORG_NAMES:
        return True
    return (
        _looks_like_department_name(stripped)
        and len(stripped) <= 4
        and not _looks_like_company_name(stripped)
    )


def _should_scope_org_locally(org: Organization) -> bool:
    name = (org.org_name or "").strip() or (org.org_code or "").strip() or org.business_key
    if not name:
        return False
    if _find_canonical_org_entry(org.business_key) or _find_canonical_org_entry(org.org_name):
        return False
    if _looks_like_company_name(name):
        return False
    return _looks_like_generic_org_name(name)


def _build_local_org_business_key(er: ExtractionResult, name: str) -> str:
    report_scope = ""
    if er.report and er.report.business_key:
        report_scope = er.report.business_key
    if not report_scope:
        for org in er.organizations:
            if org.supporting_chunks:
                report_scope = org.supporting_chunks[0].split("#", 1)[0]
                break
    if not report_scope:
        report_scope = "UNKNOWN"
    normalized_name = _normalize_match_text(name) or name.strip()
    return f"ORG-LOCAL::{report_scope}::{normalized_name}"


def _build_local_person_business_key(er: ExtractionResult, name: str) -> str:
    report_scope = ""
    if er.report and er.report.business_key:
        report_scope = er.report.business_key
    if not report_scope:
        for chunk in er.chunks:
            if chunk.report_id:
                report_scope = chunk.report_id
                break
    if not report_scope:
        report_scope = "UNKNOWN"
    normalized_name = _normalize_match_text(name) or name.strip()
    return f"PER-LOCAL::{report_scope}::{normalized_name}"


def _looks_like_person_name(name: str | None, supporting_text: str = "") -> bool:
    if not name:
        return False
    stripped = name.strip()
    if not stripped or _looks_like_orgish_name(stripped):
        return False
    if _find_canonical_org_entry(stripped):
        return False

    cjk_only = re.fullmatch(r"[\u4e00-\u9fff]{2,4}", stripped)
    titled_cjk = re.fullmatch(r"[\u4e00-\u9fff]{1,3}(工|经理|主任|总监|总工|班长|老师)", stripped)
    if cjk_only or titled_cjk:
        return True

    normalized_text = _normalize_match_text(supporting_text)
    normalized_name = _normalize_match_text(stripped)
    if not normalized_name:
        return False

    if _PERSON_TITLE_RE.search(stripped):
        return True

    return bool(
        normalized_name in normalized_text and _PERSON_CONTEXT_SIGNAL_RE.search(supporting_text)
    )


def _find_canonical_org_entry(name: str | None) -> dict | None:
    if not name:
        return None
    normalized_name = _normalize_match_text(name)
    if not normalized_name:
        return None

    lexicon = load_lexicon()
    for entry in lexicon.get("organization_aliases", []):
        candidates = {
            candidate
            for candidate in (
                _normalize_match_text(entry.get("canonical_code")),
                _normalize_match_text(entry.get("canonical_name")),
                *[_normalize_match_text(alias) for alias in entry.get("aliases", [])],
            )
            if candidate
        }
        if normalized_name in candidates:
            return entry
    return None


def _organization_match_candidates(org) -> set[str]:
    candidates = {
        candidate
        for candidate in (
            _normalize_match_text(org.business_key),
            _normalize_match_text(org.org_code),
            _normalize_match_text(org.org_name),
        )
        if candidate
    }

    entry = _find_canonical_org_entry(org.business_key) or _find_canonical_org_entry(org.org_name)
    if entry:
        candidates.update(
            candidate
            for candidate in (
                _normalize_match_text(entry.get("canonical_code")),
                _normalize_match_text(entry.get("canonical_name")),
                *[_normalize_match_text(alias) for alias in entry.get("aliases", [])],
            )
            if candidate
        )
    return candidates


def _extract_operator_names_from_text(text: str) -> set[str]:
    if not text:
        return set()
    names: set[str] = set()
    for match in _OPERATOR_NAME_RE.finditer(text):
        candidate = match.group(0).strip("：:;；，,。. ")
        if _is_noisy_org_name(candidate):
            continue
        names.add(candidate)
    return names


def materialize_organizations_from_action_owners(er: ExtractionResult) -> None:
    """当 LLM 漏掉 organizations 时, 从多来源字段与文本保守补齐 Organization。"""
    existing_keys = {org.business_key for org in er.organizations}
    existing_names = {
        _normalize_match_text(org.org_name) for org in er.organizations if org.org_name
    }
    lexicon = load_lexicon()
    alias_entries = lexicon.get("organization_aliases", [])

    def _infer_org_type(name: str, preferred_type: str | None = None) -> str | None:
        if preferred_type:
            return preferred_type
        if _looks_like_operator_name(name):
            return "运营商"
        if "供应商" in name:
            return "供应商"
        return None

    def _append_org(
        *,
        raw_name: str,
        supporting_chunks: list[str],
        preferred_type: str | None = None,
    ) -> None:
        name = (raw_name or "").strip()
        if not name:
            return

        entry = _find_canonical_org_entry(name)
        if _is_generic_supplier_name(name) and entry is None:
            return
        if _is_noisy_org_name(name) and entry is None:
            return
        if entry:
            business_key = entry.get("canonical_code") or name
            org_name = entry.get("canonical_name") or name
            org_type = entry.get("org_type") or _infer_org_type(name, preferred_type)
        elif _looks_like_orgish_name(name):
            business_key = (
                _build_local_org_business_key(er, name)
                if _looks_like_generic_org_name(name)
                else name
            )
            org_name = name
            org_type = _infer_org_type(name, preferred_type)
        else:
            return

        normalized_name = _normalize_match_text(org_name)
        if business_key in existing_keys or normalized_name in existing_names:
            return

        er.organizations.append(
            Organization(
                business_key=business_key,
                org_code=business_key,
                org_name=org_name,
                org_type=org_type,
                supporting_chunks=list(supporting_chunks),
            )
        )
        existing_keys.add(business_key)
        if normalized_name:
            existing_names.add(normalized_name)

    for action in er.actions:
        _append_org(
            raw_name=action.owner_name or "",
            supporting_chunks=list(action.supporting_chunks),
        )

    if er.report and er.report.owner_name:
        _append_org(
            raw_name=er.report.owner_name,
            supporting_chunks=list(er.report.supporting_chunks),
        )
    if er.event and er.event.reporter_name:
        _append_org(
            raw_name=er.event.reporter_name,
            supporting_chunks=list(er.event.supporting_chunks),
        )
    for product_instance in er.product_instances:
        _append_org(
            raw_name=product_instance.owner_name or "",
            supporting_chunks=list(product_instance.supporting_chunks),
            preferred_type="运营商"
            if _looks_like_operator_name(product_instance.owner_name)
            else None,
        )
    for part_serial in er.part_serials:
        _append_org(
            raw_name=part_serial.supplier_name or "",
            supporting_chunks=list(part_serial.supporting_chunks),
            preferred_type="供应商",
        )

    for chunk in er.chunks:
        text = chunk.text or ""
        if not text:
            continue
        normalized_chunk = _normalize_match_text(text)
        if not normalized_chunk:
            continue

        for entry in alias_entries:
            canonical_name = entry.get("canonical_name") or ""
            canonical_code = entry.get("canonical_code") or canonical_name
            if not canonical_code:
                continue
            aliases = [canonical_name, *entry.get("aliases", []), entry.get("canonical_code", "")]
            normalized_aliases = {
                _normalize_match_text(alias)
                for alias in aliases
                if alias and len(_normalize_match_text(alias)) >= 3
            }
            if any(alias in normalized_chunk for alias in normalized_aliases):
                _append_org(
                    raw_name=canonical_name or canonical_code,
                    supporting_chunks=[chunk.chunk_id],
                    preferred_type=entry.get("org_type"),
                )

        for operator_name in _extract_operator_names_from_text(text):
            _append_org(
                raw_name=operator_name,
                supporting_chunks=[chunk.chunk_id],
                preferred_type="运营商",
            )


def materialize_persons_from_actor_fields(er: ExtractionResult) -> None:
    """从 reporter / owner 原始字段保守补 Person。"""
    existing_keys = {person.business_key for person in er.persons}
    existing_names = {(person.person_name or "").strip() for person in er.persons}

    candidates: list[tuple[str, list[str]]] = []
    if er.event and er.event.reporter_name:
        candidates.append((er.event.reporter_name, list(er.event.supporting_chunks)))
    if er.report and er.report.owner_name:
        candidates.append((er.report.owner_name, list(er.report.supporting_chunks)))
    for action in er.actions:
        if action.owner_name:
            candidates.append((action.owner_name, list(action.supporting_chunks)))

    for raw_name, supporting_chunks in candidates:
        person_name = raw_name.strip()
        if not person_name:
            continue
        supporting_text = _supporting_chunk_text(er, supporting_chunks)
        if not _looks_like_person_name(person_name, supporting_text):
            continue

        business_key = _build_local_person_business_key(er, person_name)
        if business_key in existing_keys or person_name in existing_names:
            continue

        er.persons.append(
            Person(
                business_key=business_key,
                person_id=business_key,
                person_name=person_name,
                supporting_chunks=supporting_chunks,
            )
        )
        existing_keys.add(business_key)
        existing_names.add(person_name)


def _normalize_part_token(value: str | None) -> str:
    normalized = _normalize_match_text(value)
    return normalized.upper() if normalized else ""


def _extract_family_code(kb_part_name: str | None, kb_part_number: str | None) -> str | None:
    for text in (kb_part_name, kb_part_number):
        if not text:
            continue
        matched = _FAMILY_TOKEN_RE.search(text)
        if matched:
            return matched.group(1).upper()
    return None


def _build_failure_product_key(*, kb_part_name: str | None, kb_part_number: str | None) -> str:
    family_code = _extract_family_code(kb_part_name, kb_part_number)
    if family_code:
        return f"FP-FAMILY::{family_code}"
    normalized_pn = _normalize_part_token(kb_part_number)
    if normalized_pn:
        return f"FP-PN::{normalized_pn}"
    normalized_name = _normalize_part_token(kb_part_name)
    if normalized_name:
        return f"FP-NAME::{normalized_name}"
    return "FP-UNKNOWN"


def _parse_amount(raw_amount: str | None) -> tuple[float | None, str | None]:
    if not raw_amount:
        return None, None
    matched = _AMOUNT_RE.search(raw_amount.strip())
    if not matched:
        return None, None
    value = matched.group("value")
    unit = matched.group("unit")
    return (float(value) if value else None), (unit.lower() if unit else None)


def _build_failure_product_mention_key(
    *,
    report_scope: str,
    kb_part_name: str | None,
    kb_part_number: str | None,
    amount: str | None,
    index: int,
) -> str:
    normalized_name = _normalize_part_token(kb_part_name) or "NONAME"
    normalized_number = _normalize_part_token(kb_part_number) or "NONUM"
    normalized_amount = _normalize_part_token(amount) or "NOAMOUNT"
    return (
        f"FPM::{report_scope}::{normalized_name}::{normalized_number}::{normalized_amount}::{index}"
    )


def materialize_failure_products(er: ExtractionResult) -> None:
    """构建 FailureProduct / FailureProductMention，并做跨报告稳定归一。"""
    report_scope = (er.report.business_key if er.report else None) or "UNKNOWN"

    if not er.failure_product_mentions and er.part_serials:
        for idx, part in enumerate(er.part_serials):
            mention_key = _build_failure_product_mention_key(
                report_scope=report_scope,
                kb_part_name=None,
                kb_part_number=part.serial_number or part.part_key,
                amount=None,
                index=idx,
            )
            er.failure_product_mentions.append(
                FailureProductMention(
                    business_key=mention_key,
                    report_no=report_scope,
                    KBPartName=None,
                    KBPartNumber=part.serial_number or part.part_key,
                    Amount=None,
                    supporting_chunks=part.supporting_chunks,
                    source_doc_id=part.source_doc_id,
                    source_section=part.source_section,
                    confidence=part.confidence,
                    extraction_version=part.extraction_version,
                    schema_version=part.schema_version,
                    review_status=part.review_status,
                    owner_id=part.owner_id,
                    sensitivity=part.sensitivity,
                )
            )

    products_by_key: dict[str, FailureProduct] = {p.business_key: p for p in er.failure_products}
    deduped_mentions: list[FailureProductMention] = []
    seen_mentions: set[str] = set()

    for index, mention in enumerate(er.failure_product_mentions):
        mention.report_no = mention.report_no or report_scope
        mention.amount_value, mention.amount_unit = _parse_amount(mention.Amount)

        product_key = _build_failure_product_key(
            kb_part_name=mention.KBPartName,
            kb_part_number=mention.KBPartNumber,
        )
        mention.failure_product_key = product_key

        mention_key = mention.business_key
        if not mention_key or mention_key.startswith("UNKNOWN"):
            mention_key = _build_failure_product_mention_key(
                report_scope=mention.report_no or report_scope,
                kb_part_name=mention.KBPartName,
                kb_part_number=mention.KBPartNumber,
                amount=mention.Amount,
                index=index,
            )
        mention.business_key = mention_key
        if mention.business_key in seen_mentions:
            continue
        seen_mentions.add(mention.business_key)
        deduped_mentions.append(mention)

        product = products_by_key.get(product_key)
        if product is None:
            canonical_name = (mention.KBPartName or mention.KBPartNumber or product_key).strip()
            products_by_key[product_key] = FailureProduct(
                business_key=product_key,
                canonical_name=canonical_name,
                family_code=_extract_family_code(mention.KBPartName, mention.KBPartNumber),
                KBPartName=mention.KBPartName,
                KBPartNumber=mention.KBPartNumber,
                aliases=[canonical_name] if canonical_name else [],
                kb_part_numbers=[mention.KBPartNumber] if mention.KBPartNumber else [],
                supporting_chunks=list(mention.supporting_chunks),
                source_doc_id=mention.source_doc_id,
                source_section=list(mention.source_section),
                confidence=mention.confidence,
                extraction_version=mention.extraction_version,
                schema_version=mention.schema_version,
                review_status=mention.review_status,
                owner_id=mention.owner_id,
                sensitivity=mention.sensitivity,
            )
            continue

        if mention.KBPartName:
            alias_set = set(product.aliases)
            alias_set.add(mention.KBPartName.strip())
            product.aliases = sorted(alias_set)
            if not product.KBPartName:
                product.KBPartName = mention.KBPartName
        if mention.KBPartNumber:
            pn_set = set(product.kb_part_numbers)
            pn_set.add(mention.KBPartNumber.strip())
            product.kb_part_numbers = sorted(pn_set)
            if not product.KBPartNumber:
                product.KBPartNumber = mention.KBPartNumber
        product.supporting_chunks = _merge_unique_text_list(
            product.supporting_chunks + mention.supporting_chunks
        )
        product.source_section = _merge_unique_text_list(
            product.source_section + mention.source_section
        )
        product.confidence = max(product.confidence, mention.confidence)

    er.failure_product_mentions = deduped_mentions
    er.failure_products = sorted(products_by_key.values(), key=lambda item: item.business_key)


def normalize_person_relationships(er: ExtractionResult) -> None:
    """补齐并收紧 ProductEvent/EightDReport/ActionItem 到 Person 的关系。"""
    person_by_key = {person.business_key: person for person in er.persons}
    person_name_index = {
        _normalize_match_text(person.person_name): person
        for person in er.persons
        if person.person_name and _normalize_match_text(person.person_name)
    }

    retained: list[RelationTriple] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for relation in er.relationships:
        if relation.rel_type not in {"REPORTED_BY_PERSON", "OWNED_BY_PERSON"}:
            retained.append(relation)
            seen.add(_rel_key(relation))
            continue

        person = person_by_key.get(relation.to_key)
        if not person or relation.to_label != "Person":
            continue

        if relation.rel_type == "REPORTED_BY_PERSON":
            if er.event is None or relation.from_label != "ProductEvent":
                continue
            reporter_name = _normalize_match_text(er.event.reporter_name)
            person_name = _normalize_match_text(person.person_name)
            if reporter_name and reporter_name == person_name:
                retained.append(relation)
                seen.add(_rel_key(relation))
            continue

        if relation.from_label == "EightDReport" and er.report is not None:
            owner_name = _normalize_match_text(er.report.owner_name)
            person_name = _normalize_match_text(person.person_name)
            if owner_name and owner_name == person_name:
                retained.append(relation)
                seen.add(_rel_key(relation))
            continue

        if relation.from_label == "ActionItem":
            action = next(
                (item for item in er.actions if item.business_key == relation.from_key), None
            )
            if not action:
                continue
            owner_name = _normalize_match_text(action.owner_name)
            person_name = _normalize_match_text(person.person_name)
            if owner_name and owner_name == person_name:
                retained.append(relation)
                seen.add(_rel_key(relation))

    if er.event and er.event.reporter_name:
        person = person_name_index.get(_normalize_match_text(er.event.reporter_name))
        if person:
            relation = RelationTriple(
                from_label="ProductEvent",
                from_key=er.event.business_key,
                to_label="Person",
                to_key=person.business_key,
                rel_type="REPORTED_BY_PERSON",
            )
            key = _rel_key(relation)
            if key not in seen:
                retained.append(relation)
                seen.add(key)

    if er.report and er.report.owner_name:
        person = person_name_index.get(_normalize_match_text(er.report.owner_name))
        if person:
            relation = RelationTriple(
                from_label="EightDReport",
                from_key=er.report.business_key,
                to_label="Person",
                to_key=person.business_key,
                rel_type="OWNED_BY_PERSON",
            )
            key = _rel_key(relation)
            if key not in seen:
                retained.append(relation)
                seen.add(key)

    for action in er.actions:
        if not action.owner_name:
            continue
        person = person_name_index.get(_normalize_match_text(action.owner_name))
        if not person:
            continue
        relation = RelationTriple(
            from_label="ActionItem",
            from_key=action.business_key,
            to_label="Person",
            to_key=person.business_key,
            rel_type="OWNED_BY_PERSON",
        )
        key = _rel_key(relation)
        if key not in seen:
            retained.append(relation)
            seen.add(key)

    er.relationships = retained


def normalize_report_owner(er: ExtractionResult) -> None:
    """只在明确 owner 语义存在时保留 report.owner_name。"""
    if er.report is None or not er.report.owner_name:
        return

    owner_name = er.report.owner_name.strip()
    supporting_text = _supporting_chunk_text(er, er.report.supporting_chunks)
    has_owner_signal = bool(_OWNER_SIGNAL_RE.search(supporting_text))
    matches_known_org = any(owner_name == (org.org_name or "").strip() for org in er.organizations)

    if not has_owner_signal and (matches_known_org or _looks_like_orgish_name(owner_name)):
        er.report.owner_name = None
        er.report.owner_role = None


def normalize_event_severity(er: ExtractionResult) -> None:
    """只在 chunk 证据中有明确 severity 信号时保留 event.severity。"""
    if er.event is None or not er.event.severity:
        return

    severity = er.event.severity.strip()
    if not severity or len(severity) > 20:
        er.event.severity = None
        return

    supporting_text = _supporting_chunk_text(er, er.event.supporting_chunks)
    if not supporting_text:
        er.event.severity = None
        return

    if severity not in supporting_text or not _SEVERITY_SIGNAL_RE.search(supporting_text):
        er.event.severity = None


def _normalize_match_text(value: str | None) -> str:
    if not value:
        return ""
    lowered = value.strip().lower()
    return re.sub(r"[\s\-_()\uFF08\uFF09,.\uFF0C:\uFF1A;\uFF1B]+", "", lowered)


def _org_matches_action(action, org, er: ExtractionResult) -> bool:
    owner_name = _normalize_match_text(action.owner_name)
    org_candidates = _organization_match_candidates(org)
    if owner_name and owner_name in org_candidates:
        return True

    if owner_name:
        return False

    action_text = " ".join(
        part
        for part in (
            action.title or "",
            _supporting_chunk_text(er, action.supporting_chunks),
        )
        if part
    )
    normalized_action_text = _normalize_match_text(action_text)
    if any(candidate and candidate in normalized_action_text for candidate in org_candidates):
        return True
    return _looks_like_supplier(org) and "供应商" in action_text


def normalize_action_responsible_org_relationships(er: ExtractionResult) -> None:
    """收紧并补全 ActionItem -> RESPONSIBLE_ORG。"""
    action_by_key = {action.business_key: action for action in er.actions}
    org_by_key = {org.business_key: org for org in er.organizations}

    retained: list[RelationTriple] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for relation in er.relationships:
        if relation.rel_type != "RESPONSIBLE_ORG" or relation.from_label != "ActionItem":
            retained.append(relation)
            seen.add(_rel_key(relation))
            continue

        action = action_by_key.get(relation.from_key)
        org = org_by_key.get(relation.to_key)
        if not action or not org:
            continue
        if _org_matches_action(action, org, er):
            retained.append(relation)
            seen.add(_rel_key(relation))

    for action in er.actions:
        if not action.owner_name:
            continue
        matching_orgs = [org for org in er.organizations if _org_matches_action(action, org, er)]
        if len(matching_orgs) != 1:
            continue
        org = matching_orgs[0]
        relation = RelationTriple(
            from_label="ActionItem",
            from_key=action.business_key,
            to_label="Organization",
            to_key=org.business_key,
            rel_type="RESPONSIBLE_ORG",
        )
        key = _rel_key(relation)
        if key not in seen:
            retained.append(relation)
            seen.add(key)

    er.relationships = retained


def normalize_relationship_endpoint_keys(
    er: ExtractionResult, org_alias_map: dict[str, str]
) -> None:
    """把显式关系里指向组织的旧 key 归一到 canonical key。"""
    for relation in er.relationships:
        if relation.from_label == "Organization":
            normalized = _normalize_match_text(relation.from_key)
            relation.from_key = org_alias_map.get(normalized, relation.from_key)
        if relation.to_label == "Organization":
            normalized = _normalize_match_text(relation.to_key)
            relation.to_key = org_alias_map.get(normalized, relation.to_key)


def normalize_report_responsible_org_relationships(er: ExtractionResult) -> None:
    """只在报告层存在明确责任信号时保留 EightDReport -> RESPONSIBLE_ORG。"""
    if er.report is None:
        return

    supporting_text = _supporting_chunk_text(er, er.report.supporting_chunks)
    has_owner_signal = bool(_OWNER_SIGNAL_RE.search(supporting_text))
    if has_owner_signal and er.report.owner_name:
        owner_name = _normalize_match_text(er.report.owner_name)
        allowed_org_keys = {
            org.business_key
            for org in er.organizations
            if owner_name in _organization_match_candidates(org)
        }
    else:
        allowed_org_keys = set()

    retained: list[RelationTriple] = []
    for relation in er.relationships:
        if relation.rel_type != "RESPONSIBLE_ORG" or relation.from_label != "EightDReport":
            retained.append(relation)
            continue
        if relation.to_key in allowed_org_keys:
            retained.append(relation)
    er.relationships = retained


def infer_relationships(er: ExtractionResult) -> list[RelationTriple]:
    """根据已抽取实体推断主线 8D 关系 (LLM 未输出 relationships 时兜底).

    质量优先于召回:
    - report/event 与其主线实体的聚合关系可保守补齐
    - 多候选对象不做全连接补边
    - 只有单一候选或强语义信号时, 才补可选关系
    """
    rels: list[RelationTriple] = []
    report_bk = er.report.business_key if er.report else None
    event_bk = er.event.business_key if er.event else None
    single_failure_mode = _single_or_none(er.failure_modes)
    single_product = _single_or_none(er.product_instances)
    single_part_serial = _single_or_none(er.part_serials)
    single_org = _single_or_none(er.organizations)
    single_verified_cause = _single_or_none([c for c in er.causes if c.is_verified])

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
        if single_org and _looks_like_responsible_org(single_org):
            rels.append(
                RelationTriple(
                    from_label="EightDReport",
                    from_key=report_bk,
                    to_label="Organization",
                    to_key=single_org.business_key,
                    rel_type="RESPONSIBLE_ORG",
                )
            )
        if single_product:
            rels.append(
                RelationTriple(
                    from_label="EightDReport",
                    from_key=report_bk,
                    to_label="ProductInstance",
                    to_key=single_product.business_key,
                    rel_type="AFFECTED_PRODUCT",
                )
            )
        if single_part_serial:
            rels.append(
                RelationTriple(
                    from_label="EightDReport",
                    from_key=report_bk,
                    to_label="PartSerial",
                    to_key=single_part_serial.business_key,
                    rel_type="AFFECTED_SERIAL",
                )
            )
        for mention in er.failure_product_mentions:
            rels.append(
                RelationTriple(
                    from_label="EightDReport",
                    from_key=report_bk,
                    to_label="FailureProductMention",
                    to_key=mention.business_key,
                    rel_type="MENTIONS_FAILURE_PRODUCT",
                )
            )
            if mention.failure_product_key:
                rels.append(
                    RelationTriple(
                        from_label="FailureProductMention",
                        from_key=mention.business_key,
                        to_label="FailureProduct",
                        to_key=mention.failure_product_key,
                        rel_type="INSTANCE_OF_FAILURE_PRODUCT",
                    )
                )

    if event_bk and single_failure_mode:
        rels.append(
            RelationTriple(
                from_label="ProductEvent",
                from_key=event_bk,
                to_label="FailureMode",
                to_key=single_failure_mode.business_key,
                rel_type="RELATED_FAILURE_MODE",
            )
        )
    if event_bk and single_product:
        rels.append(
            RelationTriple(
                from_label="ProductEvent",
                from_key=event_bk,
                to_label="ProductInstance",
                to_key=single_product.business_key,
                rel_type="HAPPENED_ON",
            )
        )
    if event_bk and single_part_serial:
        rels.append(
            RelationTriple(
                from_label="ProductEvent",
                from_key=event_bk,
                to_label="PartSerial",
                to_key=single_part_serial.business_key,
                rel_type="RELATED_SERIAL",
            )
        )

    if len(er.causes) == 1 and single_failure_mode:
        rels.append(
            RelationTriple(
                from_label="CauseItem",
                from_key=er.causes[0].business_key,
                to_label="FailureMode",
                to_key=single_failure_mode.business_key,
                rel_type="RELATED_FAILURE_MODE",
            )
        )

    if single_part_serial and single_org and _looks_like_supplier(single_org):
        rels.append(
            RelationTriple(
                from_label="PartSerial",
                from_key=single_part_serial.business_key,
                to_label="Organization",
                to_key=single_org.business_key,
                rel_type="SUPPLIED_BY",
            )
        )
    if single_part_serial and single_product:
        rels.append(
            RelationTriple(
                from_label="PartSerial",
                from_key=single_part_serial.business_key,
                to_label="ProductInstance",
                to_key=single_product.business_key,
                rel_type="INSTALLED_ON",
            )
        )

    # 措施验证根因: 只在唯一已验证原因时兜底补边, 避免 action x cause 全连接噪声
    if single_verified_cause:
        for action in er.actions:
            rels.append(
                RelationTriple(
                    from_label="ActionItem",
                    from_key=action.business_key,
                    to_label="CauseItem",
                    to_key=single_verified_cause.business_key,
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
    """显式关系优先, 推断关系补缺."""
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
    """同步 business_key, 合并推断关系, 保证入图时边不缺失."""
    key_mapping = _sync_entity_business_keys(er, report_id_hint=report_id_hint)
    _sync_relationship_endpoint_keys(er, key_mapping)
    _sync_chunk_business_keys(er, report_id_hint=report_id_hint)
    materialize_persons_from_actor_fields(er)
    materialize_organizations_from_action_owners(er)
    materialize_failure_products(er)
    secondary_key_mapping = _sync_entity_business_keys(er, report_id_hint=report_id_hint)
    _sync_relationship_endpoint_keys(er, secondary_key_mapping)
    org_alias_map = normalize_organizations(er)
    normalize_report_owner(er)
    normalize_event_severity(er)
    normalize_relationship_endpoint_keys(er, org_alias_map)
    er.relationships = filter_supported_relationships(er.relationships)
    normalize_person_relationships(er)
    normalize_report_responsible_org_relationships(er)
    normalize_action_responsible_org_relationships(er)
    inferred = infer_relationships(er)
    er.relationships = merge_relationships(er.relationships, inferred)
    return er
