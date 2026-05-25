"""子图查询端点。"""

from fastapi import APIRouter, Depends, HTTPException, Query
from neo4j import AsyncDriver

from app.api.deps import get_neo4j
from app.graph.client import ALLOWED_LABELS, Neo4jClient
from app.schemas.api import SubgraphNode, SubgraphRelationship, SubgraphResponse

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("/centers")
async def list_graph_centers(
    limit: int = Query(20, ge=1, le=50, description="返回条目数上限"),
    driver: AsyncDriver = Depends(get_neo4j),
) -> dict:
    """列出可作为子图中心的 8D 报告（按关联度排序），供前端快速入口。"""
    client = Neo4jClient(driver)
    rows = await client.execute_read(
        """
        MATCH (r:EightDReport)
        OPTIONAL MATCH (r)-[rel]-(n)
        WHERE n IS NULL OR NOT n:Chunk
        WITH r, count(DISTINCT rel) AS degree
        RETURN r.business_key AS business_key,
               'EightDReport' AS label,
               coalesce(r.issue_title, r.report_no, r.business_key) AS title,
               degree AS degree
        ORDER BY degree DESC, r.updated_at DESC
        LIMIT $limit
        """,
        {"limit": limit},
    )
    return {"items": rows}


@router.get("/subgraph", response_model=SubgraphResponse)
async def get_subgraph(
    business_key: str = Query(..., description="起点节点业务键"),
    label: str = Query(..., description="起点节点 Neo4j label"),
    depth: int = Query(2, ge=0, le=4, description="邻域深度，0~4"),
    exclude_chunks: bool = Query(
        True,
        description="为 true 时过滤 Chunk 节点及 MENTIONED_IN 边，便于业务关系可视化",
    ),
    driver: AsyncDriver = Depends(get_neo4j),
) -> SubgraphResponse:
    """以 (label, business_key) 为中心，返回 depth 跳邻域子图。"""
    if label not in ALLOWED_LABELS:
        raise HTTPException(
            status_code=422,
            detail=f"label not in ALLOWED_LABELS: {label}",
        )

    client = Neo4jClient(driver)
    result = await client.get_subgraph(
        label=label,
        business_key=business_key,
        depth=depth,
        exclude_chunks=exclude_chunks,
    )

    if not result["center_exists"]:
        raise HTTPException(
            status_code=404,
            detail=f"node not found: label={label}, business_key={business_key}",
        )

    return SubgraphResponse(
        center={"business_key": business_key, "label": label},
        depth=depth,
        nodes=[SubgraphNode(**n) for n in result["nodes"]],
        relationships=[SubgraphRelationship(**r) for r in result["relationships"]],
        stats={
            "node_count": len(result["nodes"]),
            "relationship_count": len(result["relationships"]),
        },
    )


@router.get("/all", response_model=SubgraphResponse)
async def get_global_graph(
    rel_limit: int = Query(600, ge=1, le=5000, description="返回关系数量上限"),
    exclude_chunks: bool = Query(
        True,
        description="为 true 时过滤 Chunk 节点及 MENTIONED_IN/MENTIONS 边",
    ),
    driver: AsyncDriver = Depends(get_neo4j),
) -> SubgraphResponse:
    """返回全图关系视图（近似 MATCH p=()-[]->() RETURN p）。"""
    client = Neo4jClient(driver)
    result = await client.get_global_graph(
        rel_limit=rel_limit,
        exclude_chunks=exclude_chunks,
    )
    return SubgraphResponse(
        center={"business_key": "ALL", "label": "GlobalGraph"},
        depth=1,
        nodes=[SubgraphNode(**n) for n in result["nodes"]],
        relationships=[SubgraphRelationship(**r) for r in result["relationships"]],
        stats={
            "node_count": len(result["nodes"]),
            "relationship_count": len(result["relationships"]),
        },
    )


@router.get("/stats")
async def get_graph_stats(
    exclude_chunks: bool = Query(
        True,
        description="为 true 时排除 Chunk 节点及 MENTIONED_IN/MENTIONS 边",
    ),
    driver: AsyncDriver = Depends(get_neo4j),
) -> dict:
    """图谱汇总统计（节点/关系总量及按类型分布）。"""
    client = Neo4jClient(driver)
    return await client.get_graph_stats(exclude_chunks=exclude_chunks)