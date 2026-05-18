"""语义/关键词检索服务（v0.2：向量未接入前用关键词匹配）。"""
from __future__ import annotations

import re
from datetime import datetime, timezone

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
