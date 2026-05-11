"""Neo4j 客户端：包装 AsyncDriver，提供幂等写入接口。"""

from neo4j import AsyncDriver

ALLOWED_LABELS = {
    "EightDReport", "Project", "Customer", "Operator", "Part", "Material",
    "Standard", "TestMethod", "Process", "Equipment",
    "Vehicle", "Laboratory", "Person", "Team", "Supplier",
    "DefectOccurrence", "InspectionEvent", "Experiment",
    "ActionEvent", "VerificationEvent", "ClosureEvent",
    "Measurement", "Finding", "RootCause", "RiskAssessment", "Chunk",
    "FailureModeConcept", "FractographicFeatureConcept",
    "MetallurgicalDefectConcept", "RootCauseConcept", "ActionTypeConcept",
}

ALLOWED_REL_TYPES = {
    "BELONGS_TO", "REPORTED_BY", "OPERATED_BY", "DESCRIBES", "INVOLVES_TEAM",
    "PART_OF", "MADE_OF", "MANUFACTURED_BY",
    "OCCURS_ON", "INVOLVES", "EXHIBITS",
    "APPLIES", "PERFORMED_BY", "PRODUCES", "CONCLUDES", "EXAMINES",
    "TESTS", "ADDRESSES", "EXECUTED_BY",
    "SUPPORTS", "RULES_OUT", "LEADS_TO",
    "VERIFIES", "ASSESSES_RISK_OF",
    "MENTIONED_IN", "MENTIONS",
}


def _validate_label(label: str) -> None:
    if label not in ALLOWED_LABELS:
        raise ValueError(f"Label '{label}' not in ALLOWED_LABELS")


def _validate_rel_type(rel_type: str) -> None:
    if rel_type not in ALLOWED_REL_TYPES:
        raise ValueError(f"RelType '{rel_type}' not in ALLOWED_REL_TYPES")


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

    async def close(self) -> None:
        """关闭 driver。"""
        await self._driver.close()