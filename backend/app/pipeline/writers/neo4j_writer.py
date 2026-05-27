"""Neo4j Writer for v0.2 KGtestV2.

设计要点：
- 8 个业务实体 + Chunk，统一 MERGE on business_key（Chunk 用 chunk_business_key）。
- 关系来自 ExtractionResult.relationships（显式 RelationTriple 列表）。
- 节点属性沿用 snake_case，与 PG 字段、Neo4jClient.get_subgraph 的硬约束对齐。
- effective_document_id / extraction_run_id 暂时收下不用，保留签名兼容。
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse
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
    FailureProduct,
    FailureProductMention,
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
    ("FailureProduct", FailureProduct),
    ("FailureProductMention", FailureProductMention),
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


def _source_filename(minio_key: str) -> str | None:
    """从 local:// 或 minio:// key 提取文件名。"""
    if not minio_key:
        return None
    if minio_key.startswith("local://"):
        return Path(minio_key[len("local://") :]).name or None
    parsed = urlparse(minio_key)
    path_part = (parsed.path or "").rstrip("/")
    if path_part:
        return Path(path_part).name or None
    return minio_key.rstrip("/").split("/")[-1] or None


async def _cleanup_existing_graph_for_document(
    client: Neo4jClient,
    *,
    effective_document_id: UUID,
    filename: str | None,
    issue_title: str | None,
) -> dict[str, int]:
    """写入前清理同文档的历史子图，避免前端看到新旧节点混合。"""
    deleted_by_source_doc = 0
    deleted_by_filename = 0
    deleted_stale_unknown = 0

    q_by_source_doc = """
    MATCH (n)
    WHERE n.source_doc_id = $source_doc_id
    DETACH DELETE n
    RETURN count(n) AS deleted
    """
    result = await client.execute_write(
        q_by_source_doc,
        {"source_doc_id": str(effective_document_id)},
    )
    if result:
        deleted_by_source_doc = int(result[0].get("deleted", 0))

    if filename:
        q_by_filename = """
        MATCH (r:EightDReport {filename:$filename})
        OPTIONAL MATCH (r)-[*0..2]-(n)
        WITH collect(DISTINCT r) + collect(DISTINCT n) AS nodes
        UNWIND nodes AS node
        WITH DISTINCT node WHERE node IS NOT NULL
        DETACH DELETE node
        RETURN count(node) AS deleted
        """
        result = await client.execute_write(q_by_filename, {"filename": filename})
        if result:
            deleted_by_filename = int(result[0].get("deleted", 0))

    if issue_title:
        q_stale_unknown = """
        MATCH (r:EightDReport)
        WHERE r.filename IS NULL
          AND r.issue_title = $issue_title
          AND (r.business_key = 'FS-UNKNOWN' OR r.report_no = 'FS-UNKNOWN')
        OPTIONAL MATCH (c:Chunk)-[:CHUNK_OF_REPORT]->(r)
        WITH r, count(c) AS chunk_cnt
        WHERE chunk_cnt = 0
        OPTIONAL MATCH (r)-[*0..2]-(n)
        WITH collect(DISTINCT r) + collect(DISTINCT n) AS nodes
        UNWIND nodes AS node
        WITH DISTINCT node WHERE node IS NOT NULL
        DETACH DELETE node
        RETURN count(node) AS deleted
        """
        result = await client.execute_write(q_stale_unknown, {"issue_title": issue_title})
        if result:
            deleted_stale_unknown = int(result[0].get("deleted", 0))

    return {
        "deleted_by_source_doc": deleted_by_source_doc,
        "deleted_by_filename": deleted_by_filename,
        "deleted_stale_unknown": deleted_stale_unknown,
    }


async def _reconcile_legacy_unknown_chunk(
    client: Neo4jClient,
    *,
    good_chunk_business_key: str,
) -> int:
    """把历史 UNKNOWN chunk 的 MENTIONED_IN 迁到当前 chunk，再删除旧 chunk。"""
    q = """
    MATCH (good:Chunk {chunk_business_key:$good_chunk})
    MATCH (bad:Chunk)
    WHERE bad.chunk_business_key STARTS WITH 'UNKNOWN#'
      AND bad.report_id = 'UNKNOWN'
      AND bad.chunk_business_key <> $good_chunk
      AND (bad.text STARTS WITH good.text OR good.text STARTS WITH bad.text)
    OPTIONAL MATCH (n)-[:MENTIONED_IN]->(bad)
    WITH good, bad, collect(DISTINCT n) AS nodes
    FOREACH (node IN nodes |
      MERGE (node)-[:MENTIONED_IN]->(good)
    )
    WITH bad
    DETACH DELETE bad
    RETURN count(DISTINCT bad) AS deleted_bad_chunks
    """
    result = await client.execute_write(q, {"good_chunk": good_chunk_business_key})
    if not result:
        return 0
    return int(result[0].get("deleted_bad_chunks", 0))


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
    filename = _source_filename(ctx.minio_key)
    issue_title = er.report.issue_title if er.report else None

    cleanup_stats = await _cleanup_existing_graph_for_document(
        client,
        effective_document_id=effective_document_id,
        filename=filename,
        issue_title=issue_title,
    )
    logger.info("write_neo4j.pre_cleanup", **cleanup_stats, filename=filename)

    # ------------------------------------------------------------------
    # 1. 写入业务实体节点
    # ------------------------------------------------------------------

    # 主线（单实体）
    if er.report:
        report_props = _node_props(er.report)
        if filename:
            report_props["filename"] = filename
        report_props["source_doc_id"] = str(effective_document_id)
        await client.merge_node(
            "EightDReport",
            {"business_key": er.report.business_key},
            report_props,
        )
        nodes_written += 1

    if er.event:
        event_props = _node_props(er.event)
        event_props["source_doc_id"] = str(effective_document_id)
        await client.merge_node(
            "ProductEvent",
            {"business_key": er.event.business_key},
            event_props,
        )
        nodes_written += 1

    # 必抽列表
    for fm in er.failure_modes:
        fm_props = _node_props(fm)
        fm_props["source_doc_id"] = str(effective_document_id)
        await client.merge_node(
            "FailureMode",
            {"business_key": fm.business_key},
            fm_props,
        )
        nodes_written += 1

    for cause in er.causes:
        cause_props = _node_props(cause)
        cause_props["source_doc_id"] = str(effective_document_id)
        await client.merge_node(
            "CauseItem",
            {"business_key": cause.business_key},
            cause_props,
        )
        nodes_written += 1

    for action in er.actions:
        action_props = _node_props(action)
        action_props["source_doc_id"] = str(effective_document_id)
        await client.merge_node(
            "ActionItem",
            {"business_key": action.business_key},
            action_props,
        )
        nodes_written += 1

    # 可选实体
    for pi in er.product_instances:
        pi_props = _node_props(pi)
        pi_props["source_doc_id"] = str(effective_document_id)
        await client.merge_node(
            "ProductInstance",
            {"business_key": pi.business_key},
            pi_props,
        )
        nodes_written += 1

    for ps in er.part_serials:
        ps_props = _node_props(ps)
        ps_props["source_doc_id"] = str(effective_document_id)
        await client.merge_node(
            "PartSerial",
            {"business_key": ps.business_key},
            ps_props,
        )
        nodes_written += 1

    for org in er.organizations:
        org_props = _node_props(org)
        org_props["source_doc_id"] = str(effective_document_id)
        await client.merge_node(
            "Organization",
            {"business_key": org.business_key},
            org_props,
        )
        nodes_written += 1

    for person in er.persons:
        person_props = _node_props(person)
        person_props["source_doc_id"] = str(effective_document_id)
        await client.merge_node(
            "Person",
            {"business_key": person.business_key},
            person_props,
        )
        nodes_written += 1
    for failure_product in er.failure_products:
        fp_props = _node_props(failure_product)
        fp_props["source_doc_id"] = str(effective_document_id)
        await client.merge_node(
            "FailureProduct",
            {"business_key": failure_product.business_key},
            fp_props,
        )
        nodes_written += 1
    for mention in er.failure_product_mentions:
        mention_props = _node_props(mention)
        mention_props["source_doc_id"] = str(effective_document_id)
        await client.merge_node(
            "FailureProductMention",
            {"business_key": mention.business_key},
            mention_props,
        )
        nodes_written += 1

    # ------------------------------------------------------------------
    # 2. 写入 Chunk 节点（从 ctx.chunks，与 v1 行为一致）
    # ------------------------------------------------------------------
    valid_chunks: list[ChunkSchema] = []
    for c in ctx.chunks:
        if not c.chunk_id or not c.report_id:
            logger.warning(
                "write_neo4j.skip_invalid_chunk",
                chunk_id=getattr(c, "chunk_id", None),
                report_id=getattr(c, "report_id", None),
            )
            continue
        await client.merge_node(
            "Chunk",
            {"chunk_business_key": c.chunk_id},
            {
                **_chunk_props(c),
                "source_doc_id": str(effective_document_id),
            },
        )
        nodes_written += 1
        valid_chunks.append(c)

    migrated_unknown_chunks = 0
    for c in valid_chunks:
        migrated_unknown_chunks += await _reconcile_legacy_unknown_chunk(
            client,
            good_chunk_business_key=c.chunk_id,
        )
    if migrated_unknown_chunks:
        logger.info(
            "write_neo4j.migrated_legacy_unknown_chunks",
            migrated_unknown_chunks=migrated_unknown_chunks,
        )

    # 主干关系：每个 chunk 都挂到 report，避免图谱被分裂成孤岛
    if er.report:
        for c in valid_chunks:
            await client.merge_relationship(
                "Chunk",
                {"chunk_business_key": c.chunk_id},
                "CHUNK_OF_REPORT",
                "EightDReport",
                {"business_key": er.report.business_key},
                None,
            )
            rels_written += 1

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
    for failure_product in er.failure_products:
        existing_keys.add(("FailureProduct", failure_product.business_key))
    for mention in er.failure_product_mentions:
        existing_keys.add(("FailureProductMention", mention.business_key))
    for c in valid_chunks:
        existing_keys.add(("Chunk", c.chunk_id))

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
    for failure_product in er.failure_products:
        _collect_mentions(failure_product)
    for mention in er.failure_product_mentions:
        _collect_mentions(mention)
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
