"""Neo4j Writer for v0.2 KGtestV2.

设计要点：
- 8 个业务实体 + Chunk，统一 MERGE on business_key（Chunk 用 chunk_business_key）。
- 关系来自 ExtractionResult.relationships（显式 RelationTriple 列表）。
- 节点属性沿用 snake_case，与 PG 字段、Neo4jClient.get_subgraph 的硬约束对齐。
- effective_document_id / extraction_run_id 暂时收下不用，保留签名兼容。
"""

from __future__ import annotations

import json
from uuid import UUID

import structlog

from app.db.neo4j import get_neo4j_driver
from app.graph.client import Neo4jClient
from app.pipeline.context import PipelineContext
from app.schemas.entity import (
    ActionItem,
    CauseItem,
    EightDReport,
    FailureMode,
    Organization,
    PartSerial,
    Person,
    ProductEvent,
    ProductInstance,
)
from app.schemas.entity import (
    Chunk as ChunkSchema,
)

logger = structlog.get_logger(__name__)


# ---------- Label → business_key 字段名映射 ----------
# 8 个业务实体的 business_key 来自 BaseNode.business_key（已由 Pydantic 实例化时填好）
# Chunk 特殊：用 chunk_business_key（沿用 v1 约定，与 pg_writer 对齐）

_BUSINESS_LABELS: tuple[tuple[str, type], ...] = (
    ("EightDReport", EightDReport),
    ("ProductEvent", ProductEvent),
    ("FailureMode", FailureMode),
    ("CauseItem", CauseItem),
    ("ActionItem", ActionItem),
    ("ProductInstance", ProductInstance),
    ("PartSerial", PartSerial),
    ("Organization", Organization),
    ("Person", Person),
)


_EXCLUDE_PROPS = {"node_id"}  # business_key 保留写入（get_subgraph 依赖）


def _node_props(node) -> dict:
    """Pydantic 实体 → Neo4j 属性字典（snake_case）。

    - 排除 node_id（UUID 内部主键，不写入图）
    - 保留 business_key（get_subgraph 硬约束）
    - model_dump(mode='json') 处理 datetime / UUID → str
    - 嵌套 dict 转 JSON 字符串（Neo4j 不支持嵌套对象属性）
    - None 值不写入（避免 ON MATCH 时把已有属性覆盖为 null）
    """
    raw = node.model_dump(mode="json", exclude=_EXCLUDE_PROPS, exclude_none=True)
    result = {}
    for k, v in raw.items():
        if k in _EXCLUDE_PROPS:
            continue
        if isinstance(v, dict):
            result[k] = json.dumps(v, ensure_ascii=False)
        else:
            result[k] = v
    return result


def _chunk_props(c: ChunkSchema) -> dict:
    """Chunk 节点的 properties（截断 text 到前 500 字符避免节点过大）。"""
    text = c.text or ""
    text_snippet = text[:500] if len(text) > 500 else text
    props = {
        "report_id": c.report_id,
        "section_path": c.section_path or [],
        "para_idx": c.para_idx,
        "text": text_snippet,
        "token_count": c.token_count,
    }
    if c.chunk_role:
        props["chunk_role"] = c.chunk_role
    return props


async def write_neo4j(
    ctx: PipelineContext,
    effective_document_id: UUID,
    extraction_run_id: UUID,
) -> dict:
    """将 ExtractionResult + Chunks 写入 Neo4j。

    Returns
        dict: {"nodes_written": int, "relationships_written": int}
    """
    er = ctx.extraction_result
    if er is None:
        raise ValueError("write_neo4j requires ctx.extraction_result, got None")

    driver = get_neo4j_driver()
    client = Neo4jClient(driver)

    nodes_written = 0
    rels_written = 0

    # ------------------------------------------------------------------
    # 1. 写入业务实体节点
    # ------------------------------------------------------------------

    # 主线（单实体）
    if er.report:
        await client.merge_node(
            "EightDReport",
            {"business_key": er.report.business_key},
            _node_props(er.report),
        )
        nodes_written += 1

    if er.event:
        await client.merge_node(
            "ProductEvent",
            {"business_key": er.event.business_key},
            _node_props(er.event),
        )
        nodes_written += 1

    # 必抽列表
    for fm in er.failure_modes:
        await client.merge_node(
            "FailureMode",
            {"business_key": fm.business_key},
            _node_props(fm),
        )
        nodes_written += 1

    for cause in er.causes:
        await client.merge_node(
            "CauseItem",
            {"business_key": cause.business_key},
            _node_props(cause),
        )
        nodes_written += 1

    for action in er.actions:
        await client.merge_node(
            "ActionItem",
            {"business_key": action.business_key},
            _node_props(action),
        )
        nodes_written += 1

    # 可选实体
    for pi in er.product_instances:
        await client.merge_node(
            "ProductInstance",
            {"business_key": pi.business_key},
            _node_props(pi),
        )
        nodes_written += 1

    for ps in er.part_serials:
        await client.merge_node(
            "PartSerial",
            {"business_key": ps.business_key},
            _node_props(ps),
        )
        nodes_written += 1

    for org in er.organizations:
        await client.merge_node(
            "Organization",
            {"business_key": org.business_key},
            _node_props(org),
        )
        nodes_written += 1

    for person in er.persons:
        await client.merge_node(
            "Person",
            {"business_key": person.business_key},
            _node_props(person),
        )
        nodes_written += 1

    # ------------------------------------------------------------------
    # 2. 写入 Chunk 节点（从 ctx.chunks，与 v1 行为一致）
    # ------------------------------------------------------------------
    for c in ctx.chunks:
        await client.merge_node(
            "Chunk",
            {"chunk_business_key": c.chunk_id},
            _chunk_props(c),
        )
        nodes_written += 1

    # ------------------------------------------------------------------
    # 3. 写入显式关系（来自 ExtractionResult.relationships）
    # ------------------------------------------------------------------
    # 建立 (label, business_key) → 是否存在 的索引，过滤掉指向不存在节点的关系
    existing_keys: set[tuple[str, str]] = set()
    if er.report:
        existing_keys.add(("EightDReport", er.report.business_key))
    if er.event:
        existing_keys.add(("ProductEvent", er.event.business_key))
    for fm in er.failure_modes:
        existing_keys.add(("FailureMode", fm.business_key))
    for cause in er.causes:
        existing_keys.add(("CauseItem", cause.business_key))
    for action in er.actions:
        existing_keys.add(("ActionItem", action.business_key))
    for pi in er.product_instances:
        existing_keys.add(("ProductInstance", pi.business_key))
    for ps in er.part_serials:
        existing_keys.add(("PartSerial", ps.business_key))
    for org in er.organizations:
        existing_keys.add(("Organization", org.business_key))
    for person in er.persons:
        existing_keys.add(("Person", person.business_key))

    skipped_rels: list[dict] = []
    for rel in er.relationships:
        from_present = (rel.from_label, rel.from_key) in existing_keys
        to_present = (rel.to_label, rel.to_key) in existing_keys
        if not (from_present and to_present):
            skipped_rels.append(
                {
                    "rel_type": rel.rel_type,
                    "from": f"{rel.from_label}/{rel.from_key}",
                    "to": f"{rel.to_label}/{rel.to_key}",
                    "missing_from": not from_present,
                    "missing_to": not to_present,
                }
            )
            continue

        await client.merge_relationship(
            rel.from_label,
            {"business_key": rel.from_key},
            rel.rel_type,
            rel.to_label,
            {"business_key": rel.to_key},
            rel.properties or None,
        )
        rels_written += 1

    if skipped_rels:
        logger.warning(
            "write_neo4j.relationships_skipped",
            count=len(skipped_rels),
            samples=skipped_rels[:5],
        )

    # ------------------------------------------------------------------
    # 4. MENTIONED_IN 批量写入（基于实体的 supporting_chunks）
    # ------------------------------------------------------------------
    mentioned_pairs: list[dict] = []

    def _collect_mentions(entity) -> None:
        bk = getattr(entity, "business_key", None)
        if not bk:
            return
        supporting = getattr(entity, "supporting_chunks", None) or []
        for chunk_bk in supporting:
            mentioned_pairs.append({"node_bk": bk, "chunk_bk": chunk_bk})

    if er.report:
        _collect_mentions(er.report)
    if er.event:
        _collect_mentions(er.event)
    for fm in er.failure_modes:
        _collect_mentions(fm)
    for cause in er.causes:
        _collect_mentions(cause)
    for action in er.actions:
        _collect_mentions(action)
    for pi in er.product_instances:
        _collect_mentions(pi)
    for ps in er.part_serials:
        _collect_mentions(ps)
    for org in er.organizations:
        _collect_mentions(org)
    for person in er.persons:
        _collect_mentions(person)

    if mentioned_pairs:
        cypher = """
        UNWIND $items AS x
        MATCH (n) WHERE n.business_key = x.node_bk
        MATCH (c:Chunk {chunk_business_key: x.chunk_bk})
        MERGE (n)-[:MENTIONED_IN]->(c)
        """
        await client.execute_write(cypher, {"items": mentioned_pairs})
        rels_written += len(mentioned_pairs)

    logger.info(
        "write_neo4j.done",
        nodes_written=nodes_written,
        relationships_written=rels_written,
        skipped_relationships=len(skipped_rels),
    )
    return {
        "nodes_written": nodes_written,
        "relationships_written": rels_written,
    }
