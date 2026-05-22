"""table_personnel_extractor 单元测试。"""

from uuid import uuid4

from app.pipeline.context import PipelineContext
from app.pipeline.table_personnel_extractor import enrich_personnel_from_tables
from app.schemas.entity import Chunk, EightDReport
from app.schemas.extraction import ExtractionResult


def _build_ctx() -> PipelineContext:
    return PipelineContext(
        document_id=uuid4(),
        minio_key="local://sample.docx",
        report_id_hint="FS-001",
        chunks=[
            Chunk(
                chunk_id="FS-001#full_document#0",
                report_id="FS-001",
                section_path=["full_document"],
                para_idx=0,
                chunk_role="unknown",
                text="full document",
            )
        ],
    )


def test_enrich_personnel_from_team_table_extracts_people_and_involvement_edges() -> None:
    ctx = _build_ctx()
    ctx.raw_tables = [
        {
            "headers": ["姓名", "部门", "邮件地址"],
            "rows": [
                {
                    "姓名": "王怀亮",
                    "部门": "项目经理",
                    "邮件地址": "Huailiang.Wang@knorr-bremse.com",
                },
                {
                    "姓名": "黄海霞",
                    "部门": "项目经理",
                    "邮件地址": "Sandy.Huang@knorr-bremse.com",
                },
            ],
        }
    ]
    er = ExtractionResult(
        report=EightDReport(business_key="FS-001", report_no="FS-001", issue_title="EP2002")
    )

    enrich_personnel_from_tables(ctx, er)

    assert {(person.person_name, person.department, person.email) for person in er.persons} == {
        ("王怀亮", "项目经理", "Huailiang.Wang@knorr-bremse.com"),
        ("黄海霞", "项目经理", "Sandy.Huang@knorr-bremse.com"),
    }
    assert {
        (rel.from_label, rel.rel_type, rel.to_label)
        for rel in er.relationships
        if rel.rel_type == "INVOLVES_PERSON"
    } == {
        ("EightDReport", "INVOLVES_PERSON", "Person"),
    }


def test_enrich_personnel_from_author_reviewer_table_extracts_role_specific_edges() -> None:
    ctx = _build_ctx()
    ctx.raw_tables = [
        {
            "headers": ["编写：", "2022/10/26", "", "核对：", "2022/10/27"],
            "rows": [
                {"编写：": "", "2022/10/26": "日期", "": "", "核对：": "", "2022/10/27": "日期"},
                {
                    "编写：": "俞士剑",
                    "2022/10/26": "俞士剑",
                    "": "",
                    "核对：": "周幼武",
                    "2022/10/27": "周幼武",
                },
            ],
        }
    ]
    er = ExtractionResult(
        report=EightDReport(business_key="FS-001", report_no="FS-001", issue_title="EP2002")
    )

    enrich_personnel_from_tables(ctx, er)

    assert {person.person_name for person in er.persons} == {"俞士剑", "周幼武"}
    assert {
        (rel.rel_type, rel.to_key)
        for rel in er.relationships
        if rel.rel_type in {"AUTHORED_BY_PERSON", "REVIEWED_BY_PERSON"}
    } == {
        ("AUTHORED_BY_PERSON", "PER-LOCAL::FS-001::俞士剑"),
        ("REVIEWED_BY_PERSON", "PER-LOCAL::FS-001::周幼武"),
    }


def test_enrich_personnel_reuses_existing_team_person_for_author_role() -> None:
    ctx = _build_ctx()
    ctx.raw_tables = [
        {
            "headers": ["姓名", "部门", "邮件地址"],
            "rows": [
                {
                    "姓名": "俞士剑",
                    "部门": "项目质量",
                    "邮件地址": "Shijian.Yu@knorr-bremse.com",
                }
            ],
        },
        {
            "headers": ["编写：", "2022/10/26", "", "核对：", "2022/10/27"],
            "rows": [
                {
                    "编写：": "俞士剑",
                    "2022/10/26": "俞士剑",
                    "": "",
                    "核对：": "周幼武",
                    "2022/10/27": "周幼武",
                },
            ],
        },
    ]
    er = ExtractionResult(
        report=EightDReport(business_key="FS-001", report_no="FS-001", issue_title="EP2002")
    )

    enrich_personnel_from_tables(ctx, er)

    assert len(er.persons) == 2
    assert any(person.email == "Shijian.Yu@knorr-bremse.com" for person in er.persons)
    assert any(
        rel.rel_type == "AUTHORED_BY_PERSON" and rel.to_key == "PER::shijian.yu@knorr-bremse.com"
        for rel in er.relationships
    )
    assert not any(person.title in {"编写", "核对"} for person in er.persons)


def test_enrich_personnel_normalizes_email_whitespace_for_key_and_value() -> None:
    ctx = _build_ctx()
    ctx.raw_tables = [
        {
            "headers": ["姓名", "部门", "邮件地址"],
            "rows": [
                {
                    "姓名": "俞士剑",
                    "部门": "项目质量",
                    "邮件地址": " Shijian. Yu@knorr-bremse.com ",
                }
            ],
        }
    ]
    er = ExtractionResult(
        report=EightDReport(business_key="FS-001", report_no="FS-001", issue_title="EP2002")
    )

    enrich_personnel_from_tables(ctx, er)

    assert len(er.persons) == 1
    assert er.persons[0].business_key == "PER::shijian.yu@knorr-bremse.com"
    assert er.persons[0].person_id == "PER::shijian.yu@knorr-bremse.com"
    assert er.persons[0].email == "Shijian.Yu@knorr-bremse.com"
