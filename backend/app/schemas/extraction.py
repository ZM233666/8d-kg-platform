"""v0.2 KGtestV2 抽取结果 schema。"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.entity import (
    ActionItem,
    CauseItem,
    Chunk,
    EightDReport,
    FailureMode,
    Organization,
    PartSerial,
    ProductEvent,
    ProductInstance,
)


class RelationTriple(BaseModel):
    """显式三元组：(from_label, from_key) -[rel_type]-> (to_label, to_key).

    - from_label / to_label：必须在 ALLOWED_LABELS 中。
    - from_key / to_key：对应实体的 business_key。
    - rel_type：必须在 ALLOWED_REL_TYPES 中（UPPER_SNAKE_CASE）。
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    from_label: str = Field(..., description="源节点 Label")
    from_key: str = Field(..., description="源节点 business_key")
    to_label: str = Field(..., description="目标节点 Label")
    to_key: str = Field(..., description="目标节点 business_key")
    rel_type: str = Field(..., description="关系类型，UPPER_SNAKE_CASE")
    properties: dict = Field(default_factory=dict, description="关系属性（可选）")


class ExtractionResult(BaseModel):
    """单份 8D 报告的完整抽取结果（v0.2 KGtestV2 精简版）。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    # 主线（每份报告 1 个）
    report: EightDReport | None = Field(None, description="8D 报告主体")
    event: ProductEvent | None = Field(None, description="源产品事件")

    # 必抽列表（≥1）
    failure_modes: list[FailureMode] = Field(default_factory=list)
    causes: list[CauseItem] = Field(default_factory=list)
    actions: list[ActionItem] = Field(default_factory=list)

    # 可选实体（抽出来才创建）
    product_instances: list[ProductInstance] = Field(default_factory=list)
    part_serials: list[PartSerial] = Field(default_factory=list)
    organizations: list[Organization] = Field(default_factory=list)

    # 显式关系列表（B2 新增）
    relationships: list[RelationTriple] = Field(default_factory=list)

    # 治理（分块由 s2_split 写入，s4_extract 不动）
    chunks: list[Chunk] = Field(default_factory=list)

    # 统计
    stats: dict = Field(default_factory=dict)