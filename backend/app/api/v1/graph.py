"""子图查询端点。"""

from fastapi import APIRouter, Depends, HTTPException, Query
from neo4j import AsyncDriver

from app.api.deps import get_neo4j
from app.graph.client import ALLOWED_LABELS, Neo4jClient
from app.schemas.api import SubgraphNode, SubgraphRelationship, SubgraphResponse

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("/subgraph", response_model=SubgraphResponse)
async def get_subgraph(
    business_key: str = Query(..., description="起点节点业务键"),
    label: str = Query(..., description="起点节点 Neo4j label"),
    depth: int = Query(2, ge=0, le=4, description="邻域深度，0~4"),
    driver: AsyncDriver = Depends(get_neo4j),
) -> SubgraphResponse:
    """以 (label, business_key) 为中心，返回 depth 跳邻域子图。"""
    if label not in ALLOWED_LABELS:
        raise HTTPException(
            status_code=422,
            detail=f"label not in ALLOWED_LABELS: {label}",
        )

    client = Neo4jClient(driver)
    result = await client.get_subgraph(label=label, business_key=business_key, depth=depth)

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