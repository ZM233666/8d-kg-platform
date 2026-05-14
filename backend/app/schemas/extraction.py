"""v0.2 ExtractionResult 聚合容器。

LLM 输出 JSON 结构，由 s4_extract 解析为本模型；s6_write 据此写 PG/Neo4j。
所有 list 默认空，未抽取到的实体不创建节点（可选实体）。
"""
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

    # 治理（分块由 s2_split 写入，s4_extract 不动）
    chunks: list[Chunk] = Field(default_factory=list)

    # 统计（s4_extract 填充：llm_total_tokens / llm_prompt_tokens / llm_completion_tokens / llm_calls）
    stats: dict = Field(default_factory=dict)