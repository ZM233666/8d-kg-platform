"""v0.2 KGtestV2 抽取结果 schema。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.entity import (
    ActionItem,
    CauseItem,
    Chunk,
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


class RelationTriple(BaseModel):
    """显式三元组：(from_label, from_key) -[rel_type]-> (to_label, to_key)。"""

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

    report: EightDReport | None = Field(None, description="8D 报告主体")
    event: ProductEvent | None = Field(None, description="源产品事件")

    failure_modes: list[FailureMode] = Field(default_factory=list)
    causes: list[CauseItem] = Field(default_factory=list)
    actions: list[ActionItem] = Field(default_factory=list)

    product_instances: list[ProductInstance] = Field(default_factory=list)
    part_serials: list[PartSerial] = Field(default_factory=list)
    organizations: list[Organization] = Field(default_factory=list)
    persons: list[Person] = Field(default_factory=list)
    failure_products: list[FailureProduct] = Field(default_factory=list)
    failure_product_mentions: list[FailureProductMention] = Field(default_factory=list)

    relationships: list[RelationTriple] = Field(default_factory=list)

    chunks: list[Chunk] = Field(default_factory=list)

    stats: dict = Field(default_factory=dict)

    @property
    def report_id(self) -> str | None:
        """兼容 v1 ctx.report_id 属性：返回 report.report_no（若无 report 则 None）。"""
        return self.report.report_no if self.report else None
