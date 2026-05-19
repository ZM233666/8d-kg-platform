"""语义/关键词检索服务（v0.2：向量未接入前用关键词匹配）。"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Literal

from neo4j import AsyncDriver
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk as ChunkModel

# Neo4j 业务实体优先展示的属性（用于摘要与匹配）
_ENTITY_TEXT_KEYS = (
    "issue_title",
    "title",
    "symptom",
    "mode_name",
    "org_name",
    "d2_problem_statement",
    "d4_root_cause_summary",
    "report_no",
    "event_code",
    "business_key",
)


def _tokenize(query: str) -> list[str]:
    q = query.strip().lower()
    if not q:
        return []
    parts = re.split(r"[\s,，、；;]+", q)
    return [p for p in parts if len(p) >= 2] or [q]


def _score_text(text: str, tokens: list[str]) -> float:
    if not text or not tokens:
        return 0.0
    lower = text.lower()
    hits = sum(1 for t in tokens if t in lower)
    base = hits / len(tokens)
    # 完整短语命中加分
    phrase = " ".join(tokens)
    if phrase and phrase in lower:
        base = min(1.0, base + 0.25)
    return round(min(0.98, 0.35 + base * 0.6), 3)


def _pick_content(props: dict) -> str:
    for key in _ENTITY_TEXT_KEYS:
        val = props.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    for val in props.values():
        if isinstance(val, str) and len(val.strip()) > 4:
            return val.strip()[:500]
    return ""


def _summary_for_structured_result(entity_type: str, props: dict) -> dict:
    """返回结构化查询结果的摘要字段。"""
    if entity_type == "EightDReport":
        keys = (
            "business_key",
            "report_no",
            "issue_title",
            "report_date",
            "closed_at",
            "report_status",
            "owner_name",
            "confidence",
            "source_doc_id",
        )
    elif entity_type == "ProductEvent":
        keys = (
            "business_key",
            "event_id",
            "event_code",
            "event_type",
            "occurred_at",
            "severity",
            "symptom",
            "confidence",
            "source_doc_id",
        )
    elif entity_type == "ActionItem":
        keys = (
            "business_key",
            "action_id",
            "title",
            "action_type",
            "status",
            "owner_name",
            "due_date",
            "completed_at",
            "confidence",
            "source_doc_id",
        )
    else:
        keys = ("business_key", "confidence", "source_doc_id")
    return {k: props.get(k) for k in keys if props.get(k) is not None}


def _build_structured_query(
    *,
    entity_type: Literal["EightDReport", "ProductEvent", "ActionItem"],
    filters: dict,
    page: int,
    page_size: int,
    sort_by: str,
    sort_order: Literal["asc", "desc"],
) -> tuple[str, str, dict]:
    """构造结构化查询的 count / items Cypher。"""
    label = entity_type
    where_parts = [f"n:{label}"]
    params: dict[str, object] = {
        "skip": max(page - 1, 0) * page_size,
        "limit": page_size,
    }

    if entity_type == "EightDReport":
        if filters.get("report_date_from"):
            where_parts.append(
                "n.report_date IS NOT NULL AND datetime(n.report_date) >= datetime($report_date_from)"
            )
            params["report_date_from"] = filters["report_date_from"]
        if filters.get("report_date_to"):
            where_parts.append(
                "n.report_date IS NOT NULL AND datetime(n.report_date) <= datetime($report_date_to)"
            )
            params["report_date_to"] = filters["report_date_to"]
        if filters.get("report_status"):
            where_parts.append("n.report_status = $report_status")
            params["report_status"] = filters["report_status"]
    elif entity_type == "ProductEvent":
        if filters.get("occurred_at_from"):
            where_parts.append(
                "n.occurred_at IS NOT NULL AND datetime(n.occurred_at) >= datetime($occurred_at_from)"
            )
            params["occurred_at_from"] = filters["occurred_at_from"]
        if filters.get("occurred_at_to"):
            where_parts.append(
                "n.occurred_at IS NOT NULL AND datetime(n.occurred_at) <= datetime($occurred_at_to)"
            )
            params["occurred_at_to"] = filters["occurred_at_to"]
        if filters.get("event_type"):
            where_parts.append("n.event_type = $event_type")
            params["event_type"] = filters["event_type"]
        if filters.get("severity"):
            where_parts.append("n.severity = $severity")
            params["severity"] = filters["severity"]
    elif entity_type == "ActionItem":
        if filters.get("completed_at_from"):
            where_parts.append(
                "n.completed_at IS NOT NULL AND datetime(n.completed_at) >= datetime($completed_at_from)"
            )
            params["completed_at_from"] = filters["completed_at_from"]
        if filters.get("completed_at_to"):
            where_parts.append(
                "n.completed_at IS NOT NULL AND datetime(n.completed_at) <= datetime($completed_at_to)"
            )
            params["completed_at_to"] = filters["completed_at_to"]
        if filters.get("action_status"):
            where_parts.append("n.status = $action_status")
            params["action_status"] = filters["action_status"]
        if filters.get("action_type"):
            where_parts.append("n.action_type = $action_type")
            params["action_type"] = filters["action_type"]

    if entity_type == "EightDReport":
        if filters.get("closed_at_from"):
            where_parts.append(
                "n.closed_at IS NOT NULL AND datetime(n.closed_at) >= datetime($closed_at_from)"
            )
            params["closed_at_from"] = filters["closed_at_from"]
        if filters.get("closed_at_to"):
            where_parts.append(
                "n.closed_at IS NOT NULL AND datetime(n.closed_at) <= datetime($closed_at_to)"
            )
            params["closed_at_to"] = filters["closed_at_to"]

    where_clause = " AND ".join(where_parts)
    order = "ASC" if sort_order == "asc" else "DESC"
    sort_field = sort_by

    count_query = f"""
    MATCH (n)
    WHERE {where_clause}
    RETURN count(n) AS total
    """

    items_query = f"""
    MATCH (n)
    WHERE {where_clause}
    RETURN n.business_key AS business_key,
           labels(n)[0] AS entity_type,
           properties(n) AS props
    ORDER BY n.{sort_field} {order}, n.updated_at DESC
    SKIP $skip
    LIMIT $limit
    """

    return count_query, items_query, params


async def search_entities_neo4j(
    driver: AsyncDriver,
    query: str,
    limit: int,
) -> list[dict]:
    """在 Neo4j 业务节点上做关键词检索（排除 Chunk）。"""
    tokens = _tokenize(query)
    q_lower = query.strip().lower()
    if not q_lower:
        return []

    # 仅在字符串/数值属性上匹配，避免对数组等类型 toString 报错
    cypher = """
    MATCH (n)
    WHERE NOT n:Chunk
    WITH n, labels(n)[0] AS entity_type
    WHERE any(k IN keys(n) WHERE
      n[k] IS NOT NULL AND (
        (n[k] IS :: STRING AND toLower(n[k]) CONTAINS $q) OR
        (n[k] IS :: INTEGER AND toString(n[k]) CONTAINS $q) OR
        (n[k] IS :: FLOAT AND toString(n[k]) CONTAINS $q)
      )
    )
    RETURN entity_type,
           n.business_key AS business_key,
           properties(n) AS props
    LIMIT $limit
    """
    async with driver.session() as session:
        result = await session.run(cypher, {"q": q_lower, "limit": limit * 2})
        rows = [dict(r) async for r in result]

    items: list[dict] = []
    now = datetime.now(timezone.utc).isoformat()
    for row in rows:
        props = dict(row.get("props") or {})
        content = _pick_content(props)
        if not content:
            content = row.get("business_key") or ""
        score = _score_text(content, tokens)
        items.append(
            {
                "id": row.get("business_key") or "",
                "content": content,
                "entity_type": row.get("entity_type") or "Unknown",
                "match_score": score,
                "timestamp": now,
            }
        )
    return items


async def search_chunks_pg(
    session: AsyncSession,
    query: str,
    limit: int,
) -> list[dict]:
    """在 Postgres chunks 表上做文本检索。"""
    q = query.strip()
    if not q:
        return []

    pattern = f"%{q}%"
    stmt = (
        select(ChunkModel)
        .where(ChunkModel.text.ilike(pattern))
        .order_by(ChunkModel.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    chunks = result.scalars().all()

    tokens = _tokenize(query)
    now = datetime.now(timezone.utc).isoformat()
    items: list[dict] = []
    for c in chunks:
        text = (c.text or "")[:500]
        items.append(
            {
                "id": c.chunk_business_key,
                "content": text,
                "entity_type": "Chunk",
                "match_score": _score_text(text, tokens),
                "timestamp": now,
            }
        )
    return items


async def search(
    *,
    driver: AsyncDriver,
    db: AsyncSession,
    query: str,
    top_k: int = 10,
) -> list[dict]:
    """合并 Neo4j 实体 + PG 文档块检索结果。"""
    top_k = max(1, min(top_k, 50))
    entity_items = await search_entities_neo4j(driver, query, top_k)
    chunk_items = await search_chunks_pg(db, query, top_k)

    merged = entity_items + chunk_items
    merged.sort(key=lambda x: x["match_score"], reverse=True)

    # 按 id 去重，保留高分
    seen: set[str] = set()
    out: list[dict] = []
    for item in merged:
        key = f"{item['entity_type']}:{item['id']}"
        if not item["id"] or key in seen:
            continue
        seen.add(key)
        out.append(item)
        if len(out) >= top_k:
            break
    return out


async def structured_query(
    *,
    driver: AsyncDriver,
    entity_type: Literal["EightDReport", "ProductEvent"],
    filters: dict,
    page: int = 1,
    page_size: int = 20,
    sort_by: str = "updated_at",
    sort_order: Literal["asc", "desc"] = "desc",
) -> dict:
    """最小结构化查询：先支持时间范围过滤。"""
    count_query, items_query, params = _build_structured_query(
        entity_type=entity_type,
        filters=filters,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    async with driver.session() as session:
        count_result = await session.run(count_query, params)
        count_row = await count_result.single()
        total = int(count_row["total"]) if count_row else 0

        items_result = await session.run(items_query, params)
        rows = [dict(r) async for r in items_result]

    items = []
    for row in rows:
        props = dict(row.get("props") or {})
        items.append(
            {
                "business_key": row.get("business_key"),
                "entity_type": row.get("entity_type") or entity_type,
                "summary": _summary_for_structured_result(entity_type, props),
                "confidence": props.get("confidence"),
                "source_doc_id": props.get("source_doc_id"),
            }
        )

    return {
        "entity_type": entity_type,
        "items": items,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
        },
        "query_metrics": {
            "cypher_template_id": f"structured_{entity_type.lower()}_temporal_v1",
        },
    }
