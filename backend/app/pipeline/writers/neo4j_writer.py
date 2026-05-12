"""Neo4j Writer：将 ExtractionResult 写入知识图谱。"""

from __future__ import annotations

import json
import structlog
from uuid import UUID

from app.db.neo4j import get_neo4j_driver
from app.graph.client import Neo4jClient
from app.pipeline.context import PipelineContext
from app.schemas.entity import (
    ActionEvent,
    Chunk as ChunkSchema,
    ClosureEvent,
    DefectOccurrence,
    Finding,
    InspectionEvent,
    Measurement,
    RiskAssessment,
    RootCause,
    VerificationEvent,
)

logger = structlog.get_logger(__name__)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

_EXCLUDE_PROPS = {"node_id", "business_key"}


def _node_props(node) -> dict:
    """从 Pydantic 节点模型中提取 Neo4j properties。

    - 排除 node_id / business_key（由调用方单独传 business_key）
    - model_dump(mode='json') 处理 datetime / UUID → str
    - list / dict 直接存（Neo4j 原生支持）
    """
    raw = node.model_dump(mode="json", exclude=_EXCLUDE_PROPS)
    # 仍然排除 business_key 字段（不在 exclude 里时兜底）
    result = {k: v for k, v in raw.items() if k not in _EXCLUDE_PROPS}
    # 嵌套 dict（InspectionEvent.conclusion_text 等）直接存为 JSON 字符串
    for k, v in result.items():
        if isinstance(v, dict):
            result[k] = json.dumps(v, ensure_ascii=False)
    return result


def _chunk_props(c: ChunkSchema) -> dict:
    """Chunk 节点的 properties（不存全文 text，最多截取前 500 字符）。"""
    text_snippet = c.text[:500] if len(c.text) > 500 else c.text
    return {
        "report_id": c.report_id,
        "section_path": c.section_path or [],
        "para_idx": c.para_idx,
        "chunk_role": c.chunk_role,
        "text": text_snippet,
        "token_count": c.token_count,
    }


# ------------------------------------------------------------------
# Main writer
# ------------------------------------------------------------------

async def write_neo4j(
    ctx: PipelineContext,
    effective_document_id: UUID,
    extraction_run_id: UUID,
) -> dict:
    """将 ExtractionResult 中的所有实体 + 关系写入 Neo4j。

    Returns
        dict: {"nodes_written": int, "relationships_written": int}
    """
    er = ctx.extraction_result
    driver = get_neo4j_driver()
    client = Neo4jClient(driver)

    nodes_written = 0
    rels_written = 0

    # ------------------------------------------------------------------
    # 1. 写入节点
    # ------------------------------------------------------------------
    # EightDReport
    if er.report:
        await client.merge_node(
            "EightDReport",
            {"business_key": er.report.business_key},
            _node_props(er.report),
        )
        nodes_written += 1

    # DefectOccurrence
    for defect in er.defect_occurrences:
        await client.merge_node(
            "DefectOccurrence",
            {"business_key": defect.business_key},
            _node_props(defect),
        )
        nodes_written += 1

    # RootCause
    for rc in er.root_causes:
        await client.merge_node(
            "RootCause",
            {"business_key": rc.business_key},
            _node_props(rc),
        )
        nodes_written += 1

    # ActionEvent
    for action in er.actions:
        await client.merge_node(
            "ActionEvent",
            {"business_key": action.business_key},
            _node_props(action),
        )
        nodes_written += 1

    # VerificationEvent
    for v in er.verifications:
        await client.merge_node(
            "VerificationEvent",
            {"business_key": v.business_key},
            _node_props(v),
        )
        nodes_written += 1

    # ClosureEvent
    if er.closure:
        await client.merge_node(
            "ClosureEvent",
            {"business_key": er.closure.business_key},
            _node_props(er.closure),
        )
        nodes_written += 1

    # RiskAssessment
    for risk in er.risk_assessments:
        await client.merge_node(
            "RiskAssessment",
            {"business_key": risk.business_key},
            _node_props(risk),
        )
        nodes_written += 1

    # Measurement
    for m in er.measurements:
        await client.merge_node(
            "Measurement",
            {"business_key": m.business_key},
            _node_props(m),
        )
        nodes_written += 1

    # Finding
    for f in er.findings:
        await client.merge_node(
            "Finding",
            {"business_key": f.business_key},
            _node_props(f),
        )
        nodes_written += 1

    # InspectionEvent
    for ie in er.inspection_events:
        await client.merge_node(
            "InspectionEvent",
            {"business_key": ie.business_key},
            _node_props(ie),
        )
        nodes_written += 1

    # Chunk 节点
    for c in ctx.chunks:
        await client.merge_node(
            "Chunk",
            {"chunk_business_key": c.chunk_id},
            _chunk_props(c),
        )
        nodes_written += 1

    # ------------------------------------------------------------------
    # 2. 写入关系
    # ------------------------------------------------------------------

    # DESCRIBES: EightDReport → DefectOccurrence
    if er.report:
        for defect in er.defect_occurrences:
            await client.merge_relationship(
                "EightDReport",
                {"business_key": er.report.business_key},
                "DESCRIBES",
                "DefectOccurrence",
                {"business_key": defect.business_key},
                None,
            )
            rels_written += 1

    # LEADS_TO: DefectOccurrence → RootCause
    for defect in er.defect_occurrences:
        for rc in er.root_causes:
            await client.merge_relationship(
                "DefectOccurrence",
                {"business_key": defect.business_key},
                "LEADS_TO",
                "RootCause",
                {"business_key": rc.business_key},
                None,
            )
            rels_written += 1

    # ADDRESSES: ActionEvent → RootCause (所有 action 都关联第一个 root cause)
    if er.root_causes:
        first_rc = er.root_causes[0]
        for action in er.actions:
            await client.merge_relationship(
                "ActionEvent",
                {"business_key": action.business_key},
                "ADDRESSES",
                "RootCause",
                {"business_key": first_rc.business_key},
                None,
            )
            rels_written += 1

    # SUPPORTS / RULES_OUT: Finding → RootCause (按 polarity)
    if er.root_causes:
        first_rc = er.root_causes[0]
        for f in er.findings:
            polarity = getattr(f, "polarity", None)
            if polarity == "positive":
                rel_type = "SUPPORTS"
            elif polarity == "negative":
                rel_type = "RULES_OUT"
            else:
                continue
            await client.merge_relationship(
                "Finding",
                {"business_key": f.business_key},
                rel_type,
                "RootCause",
                {"business_key": first_rc.business_key},
                None,
            )
            rels_written += 1

    # PRODUCES: InspectionEvent → Measurement (按 inspection_event_id 匹配)
    for m in er.measurements:
        ie_id = getattr(m, "inspection_event_id", None)
        if ie_id:
            matched = next(
                (ie for ie in er.inspection_events if ie.business_key == ie_id),
                None,
            )
            if matched:
                await client.merge_relationship(
                    "InspectionEvent",
                    {"business_key": matched.business_key},
                    "PRODUCES",
                    "Measurement",
                    {"business_key": m.business_key},
                    None,
                )
                rels_written += 1

    # VERIFIES: VerificationEvent → ActionEvent (按 verified_action_id 匹配)
    for v in er.verifications:
        action_id = getattr(v, "verified_action_id", None)
        if action_id:
            matched = next(
                (a for a in er.actions if a.business_key == action_id),
                None,
            )
            if matched:
                await client.merge_relationship(
                    "VerificationEvent",
                    {"business_key": v.business_key},
                    "VERIFIES",
                    "ActionEvent",
                    {"business_key": matched.business_key},
                    None,
                )
                rels_written += 1

    # ASSESSES_RISK_OF: RiskAssessment → DefectOccurrence
    if er.defect_occurrences:
        first_defect = er.defect_occurrences[0]
        for risk in er.risk_assessments:
            await client.merge_relationship(
                "RiskAssessment",
                {"business_key": risk.business_key},
                "ASSESSES_RISK_OF",
                "DefectOccurrence",
                {"business_key": first_defect.business_key},
                None,
            )
            rels_written += 1

    # ------------------------------------------------------------------
    # 3. MENTIONED_IN 批量写入（UNWIND 直接 Cypher，避免逐条 merge_relationship）
    # ------------------------------------------------------------------
    mentioned_pairs: list[dict] = []

    def _collect_mentions(entity, bk_field="business_key"):
        bk = getattr(entity, bk_field, None)
        if not bk:
            return
        supporting = getattr(entity, "supporting_chunks", None) or []
        for chunk_bk in supporting:
            mentioned_pairs.append({"node_bk": bk, "chunk_bk": chunk_bk})

    # 收集所有实体的 supporting_chunks
    if er.report:
        _collect_mentions(er.report)
    for d in er.defect_occurrences:
        _collect_mentions(d)
    for rc in er.root_causes:
        _collect_mentions(rc)
    for a in er.actions:
        _collect_mentions(a)
    for v in er.verifications:
        _collect_mentions(v)
    if er.closure:
        _collect_mentions(er.closure)
    for risk in er.risk_assessments:
        _collect_mentions(risk)
    for m in er.measurements:
        _collect_mentions(m)
    for f in er.findings:
        _collect_mentions(f)
    for ie in er.inspection_events:
        _collect_mentions(ie)

    if mentioned_pairs:
        cypher = """
        UNWIND $items AS x
        MATCH (n) WHERE n.business_key = x.node_bk OR n.chunk_business_key = x.node_bk
        MATCH (c:Chunk {chunk_business_key: x.chunk_bk})
        MERGE (n)-[:MENTIONED_IN]->(c)
        """
        await client.execute_write(cypher, {"items": mentioned_pairs})
        rels_written += len(mentioned_pairs)

    logger.info(
        "write_neo4j.done",
        nodes_written=nodes_written,
        relationships_written=rels_written,
    )
    return {"nodes_written": nodes_written, "relationships_written": rels_written}
