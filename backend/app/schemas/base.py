"""Pydantic Schema 基类（v0.2 KGtestV2）。

设计原则：
- BaseNode 的治理字段全部可选，由 pipeline / writer 在持久化时填充。
- LLM 只负责输出业务字段（business_key + 实体特定字段），治理字段不进 prompt。
"""

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

ReviewStatus = Literal[
    "auto_committed",
    "pending_review",
    "in_review",
    "approved",
    "rejected",
    "modified",
    "on_hold",
    "committed",
]

Sensitivity = Literal["public", "restricted", "confidential"]


class BaseNode(BaseModel):
    """所有图谱节点的公共基类。v0.2：除 business_key 外的治理字段全部可选。"""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
    )

    node_id: UUID = Field(default_factory=uuid4, description="全局唯一 ID")
    business_key: str = Field(..., description="业务键，用于幂等合并")

    supporting_chunks: list[str] = Field(default_factory=list)
    source_doc_id: str | None = None
    source_section: list[str] = Field(default_factory=list)

    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    extraction_version: str = "v0.2.0"
    schema_version: str = "v0.2.0"

    review_status: ReviewStatus = "auto_committed"

    description: str | None = None
    summary: str | None = None

    owner_id: str | None = None
    sensitivity: Sensitivity = "restricted"

    created_at: datetime | None = None
    updated_at: datetime | None = None


class BaseEvent(BaseNode):
    """事件类基类。"""

    occurred_at: datetime | None = None
    location: str | None = None
    duration_seconds: float | None = None
