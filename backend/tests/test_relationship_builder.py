"""relationship_builder 单元测试。"""

from app.pipeline.relationship_builder import (
    enrich_extraction_result,
    filter_supported_relationships,
    infer_relationships,
    materialize_organizations_from_action_owners,
    merge_relationships,
    normalize_action_responsible_org_relationships,
    normalize_event_severity,
    normalize_organizations,
    normalize_relationship_endpoint_keys,
    normalize_relationship_item,
    normalize_relationships_raw,
    normalize_report_owner,
    normalize_report_responsible_org_relationships,
    resolve_report_business_key,
)
from app.schemas.entity import (
    ActionItem,
    CauseItem,
    Chunk,
    EightDReport,
    FailureMode,
    Organization,
    PartSerial,
    ProductEvent,
    ProductInstance,
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


def test_normalize_relationship_aliases_for_runtime_safe_mappings():
    raw = {
        "source_label": "ActionItem",
        "source_key": "A1",
        "target_label": "CauseItem",
        "target_key": "C1",
        "relation_type": "validates_cause",
    }
    n = normalize_relationship_item(raw)
    assert n is not None
    assert n["rel_type"] == "VERIFIES_CAUSE"


def test_normalize_relationship_drops_invalid_label_pair():
    raw = {
        "source_label": "ProductEvent",
        "source_key": "E1",
        "target_label": "Organization",
        "target_key": "ORG1",
        "relation_type": "RESPONSIBLE_ORG",
    }
    assert normalize_relationship_item(raw) is None


def test_normalize_relationships_raw_filters_invalid_endpoint_pairs():
    payload = {
        "relationships": [
            {
                "source_label": "ProductEvent",
                "source_key": "E1",
                "target_label": "EightDReport",
                "target_key": "R1",
                "relation_type": "HAS_8D_REPORT",
            },
            {
                "source_label": "ProductEvent",
                "source_key": "E1",
                "target_label": "Organization",
                "target_key": "ORG1",
                "relation_type": "RESPONSIBLE_ORG",
            },
            {
                "source_label": "ActionItem",
                "source_key": "A1",
                "target_label": "PartSerial",
                "target_key": "PS1",
                "relation_type": "target_product",
            },
        ]
    }

    normalized = normalize_relationships_raw(payload)

    assert normalized["relationships"] == [
        {
            "from_label": "ProductEvent",
            "from_key": "E1",
            "to_label": "EightDReport",
            "to_key": "R1",
            "rel_type": "HAS_8D_REPORT",
            "properties": {},
        }
    ]


def test_filter_supported_relationships_drops_invalid_explicit_relations():
    relationships = [
        RelationTriple(
            from_label="ProductEvent",
            from_key="E1",
            to_label="EightDReport",
            to_key="R1",
            rel_type="HAS_8D_REPORT",
        ),
        RelationTriple(
            from_label="ProductEvent",
            from_key="E1",
            to_label="Organization",
            to_key="ORG1",
            rel_type="RESPONSIBLE_ORG",
        ),
    ]

    filtered = filter_supported_relationships(relationships)

    assert [relation.model_dump() for relation in filtered] == [
        {
            "from_label": "ProductEvent",
            "from_key": "E1",
            "to_label": "EightDReport",
            "to_key": "R1",
            "rel_type": "HAS_8D_REPORT",
            "properties": {},
        }
    ]


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


def test_infer_relationships_is_conservative_for_multiple_candidates():
    er = ExtractionResult(
        report=EightDReport(business_key="R1", report_no="R1", issue_title="t"),
        event=ProductEvent(business_key="E1", event_id="E1"),
        causes=[
            CauseItem(business_key="C1", cause_id="C1", title="root1", is_verified=True),
            CauseItem(business_key="C2", cause_id="C2", title="root2", is_verified=True),
        ],
        actions=[
            ActionItem(business_key="A1", action_id="A1", title="fix1", action_type="纠正D5"),
            ActionItem(business_key="A2", action_id="A2", title="fix2", action_type="纠正D5"),
        ],
        failure_modes=[
            FailureMode(business_key="FM1", mode_code="FM1"),
            FailureMode(business_key="FM2", mode_code="FM2"),
        ],
        product_instances=[
            ProductInstance(business_key="P1", serial_number="P1"),
            ProductInstance(business_key="P2", serial_number="P2"),
        ],
        part_serials=[
            PartSerial(business_key="PS1", part_key="PS1"),
            PartSerial(business_key="PS2", part_key="PS2"),
        ],
        organizations=[
            Organization(
                business_key="ORG1", org_code="ORG1", org_name="供应商A", org_type="供应商"
            ),
            Organization(business_key="ORG2", org_code="ORG2", org_name="质量部", org_type="部门"),
        ],
    )

    inferred = infer_relationships(er)
    rel_keys = {(r.from_label, r.rel_type, r.to_label) for r in inferred}

    assert ("ProductEvent", "HAS_8D_REPORT", "EightDReport") in rel_keys
    assert ("EightDReport", "ROOT_CAUSE", "CauseItem") in rel_keys
    assert ("EightDReport", "CORRECTIVE_ACTION", "ActionItem") in rel_keys
    assert ("EightDReport", "RESPONSIBLE_ORG", "Organization") not in rel_keys
    assert ("ProductEvent", "RELATED_FAILURE_MODE", "FailureMode") not in rel_keys
    assert ("ProductEvent", "HAPPENED_ON", "ProductInstance") not in rel_keys
    assert ("ProductEvent", "RELATED_SERIAL", "PartSerial") not in rel_keys
    assert ("CauseItem", "RELATED_FAILURE_MODE", "FailureMode") not in rel_keys
    assert ("PartSerial", "SUPPLIED_BY", "Organization") not in rel_keys
    assert ("PartSerial", "INSTALLED_ON", "ProductInstance") not in rel_keys
    assert ("ActionItem", "VERIFIES_CAUSE", "CauseItem") not in rel_keys


def test_infer_relationships_adds_safe_single_candidate_edges():
    er = ExtractionResult(
        report=EightDReport(business_key="R1", report_no="R1", issue_title="t"),
        event=ProductEvent(business_key="E1", event_id="E1"),
        causes=[CauseItem(business_key="C1", cause_id="C1", title="root", is_verified=True)],
        actions=[ActionItem(business_key="A1", action_id="A1", title="fix", action_type="纠正D5")],
        failure_modes=[FailureMode(business_key="FM1", mode_code="FM1")],
        product_instances=[ProductInstance(business_key="P1", serial_number="P1")],
        part_serials=[PartSerial(business_key="PS1", part_key="PS1")],
        organizations=[
            Organization(
                business_key="ORG1",
                org_code="ORG1",
                org_name="苏州某密封件供应商",
                org_type="供应商",
            )
        ],
    )

    inferred = infer_relationships(er)
    rel_keys = {(r.from_label, r.from_key, r.rel_type, r.to_label, r.to_key) for r in inferred}

    assert ("ProductEvent", "E1", "HAS_8D_REPORT", "EightDReport", "R1") in rel_keys
    assert ("EightDReport", "R1", "ROOT_CAUSE", "CauseItem", "C1") in rel_keys
    assert ("EightDReport", "R1", "CORRECTIVE_ACTION", "ActionItem", "A1") in rel_keys
    assert ("EightDReport", "R1", "AFFECTED_PRODUCT", "ProductInstance", "P1") in rel_keys
    assert ("EightDReport", "R1", "AFFECTED_SERIAL", "PartSerial", "PS1") in rel_keys
    assert ("ProductEvent", "E1", "RELATED_FAILURE_MODE", "FailureMode", "FM1") in rel_keys
    assert ("ProductEvent", "E1", "HAPPENED_ON", "ProductInstance", "P1") in rel_keys
    assert ("ProductEvent", "E1", "RELATED_SERIAL", "PartSerial", "PS1") in rel_keys
    assert ("CauseItem", "C1", "RELATED_FAILURE_MODE", "FailureMode", "FM1") in rel_keys
    assert ("PartSerial", "PS1", "SUPPLIED_BY", "Organization", "ORG1") in rel_keys
    assert ("PartSerial", "PS1", "INSTALLED_ON", "ProductInstance", "P1") in rel_keys
    assert ("ActionItem", "A1", "VERIFIES_CAUSE", "CauseItem", "C1") in rel_keys


def test_infer_relationships_does_not_treat_single_customer_org_as_responsible_org():
    er = ExtractionResult(
        report=EightDReport(business_key="R1", report_no="R1", issue_title="t"),
        event=ProductEvent(business_key="E1", event_id="E1", reporter_name="克诺尔苏州"),
        organizations=[
            Organization(
                business_key="ORG1",
                org_code="ORG1",
                org_name="克诺尔苏州",
                org_type="客户",
            )
        ],
    )

    inferred = infer_relationships(er)
    rel_keys = {(r.from_label, r.rel_type, r.to_label) for r in inferred}

    assert ("ProductEvent", "HAS_8D_REPORT", "EightDReport") in rel_keys
    assert ("EightDReport", "RESPONSIBLE_ORG", "Organization") not in rel_keys


def test_normalize_organizations_converts_company_name_out_of_internal_department() -> None:
    er = ExtractionResult(
        organizations=[
            Organization(
                business_key="ORG1",
                org_code="ORG1",
                org_name="Knorr-Bremse Systems for Rail Vehicles (Suzhou) Co., Ltd.",
                org_type="内部部门",
            ),
            Organization(
                business_key="ORG2",
                org_code="ORG2",
                org_name="苏州某密封件供应商",
                org_type="内部部门",
            ),
        ]
    )

    normalize_organizations(er)

    assert er.organizations[0].org_type == "公司"
    assert er.organizations[1].org_type == "供应商"


def test_normalize_organizations_canonicalizes_known_alias(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.pipeline.relationship_builder.load_lexicon",
        lambda: {
            "organization_aliases": [
                {
                    "canonical_code": "ORG-KB-SUZHOU",
                    "canonical_name": "Knorr-Bremse Systems for Rail Vehicles (Suzhou) Co., Ltd.",
                    "org_type": "公司",
                    "aliases": ["克诺尔苏州", "KB苏州"],
                }
            ]
        },
    )

    er = ExtractionResult(
        organizations=[
            Organization(
                business_key="克诺尔苏州",
                org_code="克诺尔苏州",
                org_name="克诺尔苏州",
                org_type="内部部门",
            )
        ]
    )

    normalize_organizations(er)

    assert er.organizations[0].business_key == "ORG-KB-SUZHOU"
    assert er.organizations[0].org_code == "ORG-KB-SUZHOU"
    assert (
        er.organizations[0].org_name == "Knorr-Bremse Systems for Rail Vehicles (Suzhou) Co., Ltd."
    )
    assert er.organizations[0].org_type == "公司"


def test_materialize_organizations_from_action_owners_adds_supplier_org() -> None:
    er = ExtractionResult(
        actions=[
            ActionItem(
                business_key="A1",
                action_id="A1",
                title="对供应商库存活塞销进行100%外观检",
                action_type="纠正D5",
                owner_name="供应商",
                supporting_chunks=["R1#纠正措施#0"],
            )
        ]
    )

    materialize_organizations_from_action_owners(er)

    assert [(org.business_key, org.org_name, org.org_type) for org in er.organizations] == [
        ("供应商", "供应商", "供应商")
    ]


def test_materialize_organizations_from_action_owners_canonicalizes_known_alias(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.pipeline.relationship_builder.load_lexicon",
        lambda: {
            "organization_aliases": [
                {
                    "canonical_code": "ORG-KB-SUZHOU",
                    "canonical_name": "Knorr-Bremse Systems for Rail Vehicles (Suzhou) Co., Ltd.",
                    "org_type": "公司",
                    "aliases": ["克诺尔苏州", "KB苏州"],
                }
            ]
        },
    )

    er = ExtractionResult(
        actions=[
            ActionItem(
                business_key="A3",
                action_id="A3",
                title="由克诺尔苏州更新来料检验标准",
                action_type="纠正D5",
                owner_name="克诺尔苏州",
                supporting_chunks=["R1#纠正措施#1"],
            )
        ]
    )

    materialize_organizations_from_action_owners(er)

    assert [(org.business_key, org.org_name, org.org_type) for org in er.organizations] == [
        (
            "ORG-KB-SUZHOU",
            "Knorr-Bremse Systems for Rail Vehicles (Suzhou) Co., Ltd.",
            "公司",
        )
    ]


def test_normalize_report_owner_clears_cover_company_without_owner_signal() -> None:
    er = ExtractionResult(
        report=EightDReport(
            business_key="R1",
            report_no="R1",
            issue_title="t",
            owner_name="Knorr-Bremse Systems for Rail Vehicles (Suzhou) Co., Ltd.",
        ),
        organizations=[
            Organization(
                business_key="ORG1",
                org_code="ORG1",
                org_name="Knorr-Bremse Systems for Rail Vehicles (Suzhou) Co., Ltd.",
                org_type="公司",
            )
        ],
        chunks=[
            Chunk(
                chunk_id="R1#unknown#0",
                report_id="R1",
                section_path=["unknown"],
                para_idx=0,
                chunk_role="unknown",
                text="封面\n联系地址\nKnorr-Bremse Systems for Rail Vehicles (Suzhou) Co., Ltd.",
            )
        ],
    )

    normalize_report_owner(er)

    assert er.report is not None
    assert er.report.owner_name is None


def test_normalize_report_owner_keeps_explicit_owner_signal() -> None:
    er = ExtractionResult(
        report=EightDReport(
            business_key="R1",
            report_no="R1",
            issue_title="t",
            owner_name="王经理",
        ),
        chunks=[
            Chunk(
                chunk_id="R1#纠正措施#0",
                report_id="R1",
                section_path=["纠正措施"],
                para_idx=0,
                chunk_role="action",
                text="负责人\uff1a王经理\n负责跟踪整改关闭。",
            )
        ],
    )

    normalize_report_owner(er)

    assert er.report is not None
    assert er.report.owner_name == "王经理"


def test_normalize_event_severity_clears_unsupported_noise() -> None:
    er = ExtractionResult(
        event=ProductEvent(
            business_key="E1",
            event_id="E1",
            severity="维护等级",
            symptom="压力超差",
            supporting_chunks=["R1#问题描述#0"],
        ),
        chunks=[
            Chunk(
                chunk_id="R1#问题描述#0",
                report_id="R1",
                section_path=["问题描述"],
                para_idx=0,
                chunk_role="evidence",
                text="首次上电自检失败\uff0c报二级调节器压力超差故障。",
            )
        ],
    )

    normalize_event_severity(er)

    assert er.event is not None
    assert er.event.severity is None


def test_normalize_event_severity_keeps_explicit_grade_signal() -> None:
    er = ExtractionResult(
        event=ProductEvent(
            business_key="E1",
            event_id="E1",
            severity="维护等级",
            symptom="压力超差",
            supporting_chunks=["R1#风险分析#0"],
        ),
        chunks=[
            Chunk(
                chunk_id="R1#风险分析#0",
                report_id="R1",
                section_path=["风险分析"],
                para_idx=0,
                chunk_role="conclusion",
                text="该故障在KB内部定义为维护等级\uff0c不影响列车正常运营。",
            )
        ],
    )

    normalize_event_severity(er)

    assert er.event is not None
    assert er.event.severity == "维护等级"


def test_normalize_action_responsible_org_relationships_adds_safe_owner_match() -> None:
    er = ExtractionResult(
        actions=[
            ActionItem(
                business_key="A1",
                action_id="A1",
                title="对供应商库存活塞销进行100%外观检",
                action_type="纠正D5",
                owner_name="供应商",
                supporting_chunks=["R1#纠正措施#0"],
            )
        ],
        organizations=[
            Organization(
                business_key="ORG-SUP",
                org_code="ORG-SUP",
                org_name="供应商",
                org_type="供应商",
            )
        ],
        chunks=[
            Chunk(
                chunk_id="R1#纠正措施#0",
                report_id="R1",
                section_path=["纠正措施"],
                para_idx=0,
                chunk_role="action",
                text="对供应商库存活塞销进行100%外观检。",
            )
        ],
    )

    normalize_action_responsible_org_relationships(er)

    assert {
        (rel.from_label, rel.from_key, rel.rel_type, rel.to_label, rel.to_key)
        for rel in er.relationships
    } == {
        ("ActionItem", "A1", "RESPONSIBLE_ORG", "Organization", "ORG-SUP"),
    }


def test_normalize_action_responsible_org_relationships_matches_canonical_org_alias(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.pipeline.relationship_builder.load_lexicon",
        lambda: {
            "organization_aliases": [
                {
                    "canonical_code": "ORG-KB-SUZHOU",
                    "canonical_name": "Knorr-Bremse Systems for Rail Vehicles (Suzhou) Co., Ltd.",
                    "org_type": "公司",
                    "aliases": ["克诺尔苏州", "KB苏州"],
                }
            ]
        },
    )

    er = ExtractionResult(
        actions=[
            ActionItem(
                business_key="A3",
                action_id="A3",
                title="由克诺尔苏州更新来料检验标准",
                action_type="纠正D5",
                owner_name="克诺尔苏州",
                supporting_chunks=["R1#纠正措施#1"],
            )
        ],
        organizations=[
            Organization(
                business_key="ORG-KB-SUZHOU",
                org_code="ORG-KB-SUZHOU",
                org_name="Knorr-Bremse Systems for Rail Vehicles (Suzhou) Co., Ltd.",
                org_type="公司",
            )
        ],
    )

    normalize_action_responsible_org_relationships(er)

    assert {
        (rel.from_label, rel.from_key, rel.rel_type, rel.to_label, rel.to_key)
        for rel in er.relationships
    } == {
        ("ActionItem", "A3", "RESPONSIBLE_ORG", "Organization", "ORG-KB-SUZHOU"),
    }


def test_normalize_action_responsible_org_relationships_owner_name_prevents_context_overmatch(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.pipeline.relationship_builder.load_lexicon",
        lambda: {
            "organization_aliases": [
                {
                    "canonical_code": "ORG-KB-SUZHOU",
                    "canonical_name": "Knorr-Bremse Systems for Rail Vehicles (Suzhou) Co., Ltd.",
                    "org_type": "公司",
                    "aliases": ["克诺尔苏州", "KB苏州"],
                }
            ]
        },
    )

    er = ExtractionResult(
        actions=[
            ActionItem(
                business_key="A3",
                action_id="A3",
                title="对EP2002阀出货前增加相关检测项点并再次进行系统测试",
                action_type="纠正D5",
                owner_name="克诺尔苏州",
                supporting_chunks=["R1#纠正措施#1"],
            )
        ],
        organizations=[
            Organization(
                business_key="供应商",
                org_code="供应商",
                org_name="供应商",
                org_type="供应商",
            ),
            Organization(
                business_key="ORG-KB-SUZHOU",
                org_code="ORG-KB-SUZHOU",
                org_name="Knorr-Bremse Systems for Rail Vehicles (Suzhou) Co., Ltd.",
                org_type="公司",
            ),
        ],
        chunks=[
            Chunk(
                chunk_id="R1#纠正措施#1",
                report_id="R1",
                section_path=["纠正措施"],
                para_idx=1,
                chunk_role="action",
                text="供应商更新活塞销方案; 克诺尔苏州负责出货前增加检测项点并再次进行系统测试。",
            )
        ],
    )

    normalize_action_responsible_org_relationships(er)

    assert {
        (rel.from_label, rel.from_key, rel.rel_type, rel.to_label, rel.to_key)
        for rel in er.relationships
    } == {
        ("ActionItem", "A3", "RESPONSIBLE_ORG", "Organization", "ORG-KB-SUZHOU"),
    }


def test_normalize_action_responsible_org_relationships_drops_unsupported_explicit_edge() -> None:
    er = ExtractionResult(
        actions=[
            ActionItem(
                business_key="A1",
                action_id="A1",
                title="对库存活塞销进行100%外观检",
                action_type="纠正D5",
                owner_name="质量部",
                supporting_chunks=["R1#纠正措施#0"],
            )
        ],
        organizations=[
            Organization(
                business_key="ORG-SUP",
                org_code="ORG-SUP",
                org_name="供应商",
                org_type="供应商",
            )
        ],
        relationships=[
            RelationTriple(
                from_label="ActionItem",
                from_key="A1",
                to_label="Organization",
                to_key="ORG-SUP",
                rel_type="RESPONSIBLE_ORG",
            )
        ],
        chunks=[
            Chunk(
                chunk_id="R1#纠正措施#0",
                report_id="R1",
                section_path=["纠正措施"],
                para_idx=0,
                chunk_role="action",
                text="由质量部跟踪库存活塞销外观检。",
            )
        ],
    )

    normalize_action_responsible_org_relationships(er)

    assert er.relationships == []


def test_normalize_relationship_endpoint_keys_rewrites_org_alias_to_canonical() -> None:
    er = ExtractionResult(
        relationships=[
            RelationTriple(
                from_label="EightDReport",
                from_key="R1",
                to_label="Organization",
                to_key="克诺尔苏州",
                rel_type="RESPONSIBLE_ORG",
            )
        ]
    )

    normalize_relationship_endpoint_keys(er, {"克诺尔苏州": "ORG-KB-SUZHOU"})

    assert er.relationships[0].to_key == "ORG-KB-SUZHOU"


def test_normalize_report_responsible_org_relationships_drops_cover_org_without_owner_signal() -> (
    None
):
    er = ExtractionResult(
        report=EightDReport(
            business_key="R1",
            report_no="R1",
            issue_title="t",
            owner_name=None,
            supporting_chunks=["R1#unknown#0"],
        ),
        organizations=[
            Organization(
                business_key="ORG-KB-SUZHOU",
                org_code="ORG-KB-SUZHOU",
                org_name="Knorr-Bremse Systems for Rail Vehicles (Suzhou) Co., Ltd.",
                org_type="公司",
            )
        ],
        relationships=[
            RelationTriple(
                from_label="EightDReport",
                from_key="R1",
                to_label="Organization",
                to_key="ORG-KB-SUZHOU",
                rel_type="RESPONSIBLE_ORG",
            )
        ],
        chunks=[
            Chunk(
                chunk_id="R1#unknown#0",
                report_id="R1",
                section_path=["unknown"],
                para_idx=0,
                chunk_role="unknown",
                text="封面\n联系地址\nKnorr-Bremse Systems for Rail Vehicles (Suzhou) Co., Ltd.",
            )
        ],
    )

    normalize_report_responsible_org_relationships(er)

    assert er.relationships == []
