"""Neo4j 客户端：包装 AsyncDriver，提供幂等写入接口。"""

from datetime import datetime, timezone

from neo4j import AsyncDriver

ALLOWED_LABELS: set[str] = {
    # v0.2 KGtestV2 业务实体（8 个）
    "EightDReport",
    "ProductEvent",
    "ProductInstance",
    "PartSerial",
    "FailureMode",
    "CauseItem",
    "ActionItem",
    "Organization",
    # 治理
    "Chunk",
}

ALLOWED_REL_TYPES: set[str] = {
    # 主线
    "HAS_8D_REPORT",
    "RELATED_FAILURE_MODE",
    "ROOT_CAUSE",
    "CORRECTIVE_ACTION",
    "PREVENTIVE_ACTION",
    "VERIFIES_CAUSE",
    # 可选
    "HAPPENED_ON",
    "RELATED_SERIAL",
    "AFFECTED_PRODUCT",
    "AFFECTED_SERIAL",
    "RESPONSIBLE_ORG",
    "TARGET_SERIAL",
    "TARGET_PRODUCT",
    "INSTALLED_ON",
    "SUPPLIED_BY",
    # 治理
    "MENTIONED_IN",
    "MENTIONS",
}


def _validate_label(label: str) -> None:
    if label not in ALLOWED_LABELS:
        raise ValueError(f"Label '{label}' not in ALLOWED_LABELS")


def _validate_rel_type(rel_type: str) -> None:
    if rel_type not in ALLOWED_REL_TYPES:
        raise ValueError(f"RelType '{rel_type}' not in ALLOWED_REL_TYPES")


def _neo4j_to_json(value):
    """将 Neo4j 类型递归转换为 JSON 可序列化的 Python 原生类型。

    Neo4j DateTime/Date/Time 等类型无法被 Pydantic 直接序列化，
    此函数将其转换为 ISO 8601 字符串。
    """
    if value is None:
        return None
    # Neo4j DateTime 类型：转 ISO 字符串
    if hasattr(value, "isoformat"):
        return value.isoformat()
    # list / tuple
    if isinstance(value, (list, tuple)):
        return [_neo4j_to_json(v) for v in value]
    # dict
    if isinstance(value, dict):
        return {k: _neo4j_to_json(v) for k, v in value.items()}
    return value


class Neo4jClient:
    """Neo4j 异步客户端。driver 由调用方注入，不在模块顶层创建。"""

    def __init__(self, driver: AsyncDriver, database: str = "neo4j"):
        self._driver = driver
        self._database = database

    async def execute_read(self, query: str, params: dict | None = None) -> list[dict]:
        """执行只读查询（managed transaction）。"""
        params = params or {}

        async def _tx(tx):
            result = await tx.run(query, params)
            return [dict(r) async for r in result]

        async with self._driver.session(database=self._database) as session:
            return await session.execute_read(_tx)

    async def execute_write(self, query: str, params: dict | None = None) -> list[dict]:
        """执行写查询（managed transaction）。"""
        params = params or {}

        async def _tx(tx):
            result = await tx.run(query, params)
            return [dict(r) async for r in result]

        async with self._driver.session(database=self._database) as session:
            return await session.execute_write(_tx)

    async def merge_node(
        self,
        label: str,
        business_key: dict,
        properties: dict,
    ) -> dict:
        """幂等写入节点。MERGE + ON CREATE SET + ON MATCH SET。"""
        _validate_label(label)
        key_str = "{" + ", ".join(f"{k}: $bk_{k}" for k in business_key) + "}"

        query = f"""
        MERGE (n:`{label}` {key_str})
        ON CREATE SET n += $props, n.created_at = datetime()
        ON MATCH SET n += $props, n.updated_at = datetime()
        RETURN n
        """

        params = {
            **{f"bk_{k}": v for k, v in business_key.items()},
            "props": properties,
        }
        results = await self.execute_write(query, params)
        return results[0]["n"] if results else {}

    async def merge_relationship(
        self,
        start_label: str,
        start_key: dict,
        rel_type: str,
        end_label: str,
        end_key: dict,
        properties: dict | None = None,
    ) -> None:
        """幂等写入关系。"""
        _validate_label(start_label)
        _validate_label(end_label)
        _validate_rel_type(rel_type)

        start_key_str = "{" + ", ".join(f"{k}: $sk_{k}" for k in start_key) + "}"
        end_key_str = "{" + ", ".join(f"{k}: $ek_{k}" for k in end_key) + "}"
        props = properties or {}

        query = f"""
        MATCH (a:`{start_label}` {start_key_str}),
              (b:`{end_label}` {end_key_str})
        MERGE (a)-[r:`{rel_type}`]->(b)
        ON CREATE SET r += $props, r.created_at = datetime()
        ON MATCH SET r += $props, r.updated_at = datetime()
        """

        params = {
            **{f"sk_{k}": v for k, v in start_key.items()},
            **{f"ek_{k}": v for k, v in end_key.items()},
            "props": props,
        }
        await self.execute_write(query, params)

    async def get_subgraph(
        self,
        label: str,
        business_key: str,
        depth: int = 2,
        *,
        exclude_chunks: bool = False,
    ) -> dict:
        """以 (label, business_key) 为中心，返回 depth 跳邻域子图。

        参数：
            label: 节点 Neo4j label（必须在 ALLOWED_LABELS 内）
            business_key: 节点业务键
            depth: 邻域深度，0 ≤ depth ≤ 4

        返回：
            {
                "center_exists": bool,
                "nodes": [{"business_key": ..., "labels": [...], "properties": {...}}],
                "relationships": [{"type": ..., "start_bk": ..., "start_label": ...,
                                   "end_bk": ..., "end_label": ..., "properties": {...}}],
            }
        """
        if label not in ALLOWED_LABELS:
            raise ValueError(f"label not in ALLOWED_LABELS: {label}")
        if not isinstance(depth, int) or depth < 0 or depth > 4:
            raise ValueError(f"depth out of range [0, 4]: {depth}")

        nodes_query = f"""
            MATCH (center)
            WHERE $label IN labels(center) AND center.business_key = $bk
            OPTIONAL MATCH (center)-[*0..{depth}]-(n)
            WITH center, collect(DISTINCT n) AS neighbors
            RETURN [center] + [x IN neighbors WHERE x IS NOT NULL AND x <> center] AS all_nodes
        """

        rels_query = f"""
            MATCH (center)
            WHERE $label IN labels(center) AND center.business_key = $bk
            OPTIONAL MATCH (center)-[*0..{depth}]-(n)
            WITH center, collect(DISTINCT n) + [center] AS ns
            UNWIND ns AS a
            UNWIND ns AS b
            OPTIONAL MATCH (a)-[r]->(b)
            WITH DISTINCT r, a, b
            WHERE r IS NOT NULL
            RETURN type(r) AS rel_type,
                   a.business_key AS start_bk, labels(a) AS start_labels,
                   b.business_key AS end_bk, labels(b) AS end_labels,
                   properties(r) AS props
        """

        params = {"label": label, "bk": business_key}

        node_result = await self.execute_read(nodes_query, params)
        if not node_result:
            return {"center_exists": False, "nodes": [], "relationships": []}

        raw_nodes = node_result[0].get("all_nodes", [])
        if not raw_nodes:
            return {"center_exists": False, "nodes": [], "relationships": []}

        nodes = []
        for n in raw_nodes:
            if n is None:
                continue
            nodes.append({
                "business_key": n.get("business_key"),
                "labels": list(n.labels) if hasattr(n, "labels") else [],
                "properties": _neo4j_to_json(dict(n)),
            })

        rel_records = await self.execute_read(rels_query, params)
        relationships = []
        for rec in rel_records:
            rel_props = rec["props"]
            relationships.append({
                "type": rec["rel_type"],
                "start_bk": rec["start_bk"],
                "start_label": rec["start_labels"][0] if rec["start_labels"] else None,
                "end_bk": rec["end_bk"],
                "end_label": rec["end_labels"][0] if rec["end_labels"] else None,
                "properties": _neo4j_to_json(dict(rel_props)) if rel_props else {},
            })

        if exclude_chunks:
            nodes = [n for n in nodes if "Chunk" not in n.get("labels", [])]
            node_bks = {n["business_key"] for n in nodes if n.get("business_key")}
            relationships = [
                r
                for r in relationships
                if r.get("type") not in ("MENTIONED_IN", "MENTIONS")
                and r.get("start_label") != "Chunk"
                and r.get("end_label") != "Chunk"
                and r.get("start_bk") in node_bks
                and r.get("end_bk") in node_bks
            ]

        return {
            "center_exists": True,
            "nodes": nodes,
            "relationships": relationships,
        }

    async def close(self) -> None:
        """关闭 driver。"""
        await self._driver.close()


# ---------- v0.2 唯一约束初始化（B2 新增） ----------

# Label → 唯一键属性名映射（snake_case，与节点写入约定一致）
_UNIQUE_KEY_MAP: dict[str, str] = {
    "EightDReport": "business_key",
    "ProductEvent": "business_key",
    "FailureMode": "business_key",
    "CauseItem": "business_key",
    "ActionItem": "business_key",
    "ProductInstance": "business_key",
    "PartSerial": "business_key",
    "Organization": "business_key",
    "Chunk": "chunk_business_key",
}


async def ensure_constraints(driver) -> dict:
    """为 9 个 Label 创建 unique constraint，幂等。

    参数：
        driver: neo4j.AsyncDriver 实例（从 get_neo4j_driver() 获取）

    返回：
        {"created": N, "existing": M, "names": [...]}
    """
    created = 0
    existing = 0
    names: list[str] = []
    async with driver.session() as session:
        for label, key in _UNIQUE_KEY_MAP.items():
            constraint_name = f"uniq_{label.lower()}_{key}"
            names.append(constraint_name)
            cypher = (
                f"CREATE CONSTRAINT {constraint_name} IF NOT EXISTS "
                f"FOR (n:`{label}`) REQUIRE n.`{key}` IS UNIQUE"
            )
            result = await session.run(cypher)
            summary = await result.consume()
            if summary.counters.constraints_added > 0:
                created += 1
            else:
                existing += 1
    return {"created": created, "existing": existing, "names": names}


async def drop_all_v1_constraints(driver) -> int:
    """删除所有非 v0.2 的旧 constraint。返回删除数量。"""
    v2_names = {f"uniq_{label.lower()}_{key}" for label, key in _UNIQUE_KEY_MAP.items()}
    dropped = 0
    async with driver.session() as session:
        result = await session.run("SHOW CONSTRAINTS YIELD name")
        all_names = [rec["name"] async for rec in result]
        for name in all_names:
            if name not in v2_names:
                await session.run(f"DROP CONSTRAINT {name} IF EXISTS")
                dropped += 1
    return dropped