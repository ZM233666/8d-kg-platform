"""Pydantic Schema 基类（SCHEMA.md §2）。"""

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
    """所有图谱节点的公共基类（SCHEMA.md §2.1）。"""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
    )

    # 标识
    node_id: UUID = Field(default_factory=uuid4, description="全局唯一 ID")
    business_key: str = Field(..., description="业务键，用于幂等合并")

    # 溯源
    supporting_chunks: list[str] = Field(default_factory=list)
    source_doc_id: str
    source_section: list[str] = Field(default_factory=list)

    # 抽取元信息
    confidence: float = Field(..., ge=0.0, le=1.0)
    extraction_version: str
    schema_version: str = "v0.1.0"

    # 审核
    review_status: ReviewStatus = "auto_committed"

    # 描述
    description: str | None = None
    summary: str | None = None

    # 治理
    owner_id: str
    sensitivity: Sensitivity = "restricted"

    # 时间戳
    created_at: datetime
    updated_at: datetime


class BaseEvent(BaseNode):
    """事件类基类（SCHEMA.md §2.2）。"""

    occurred_at: datetime | None = None
    location: str | None = None
    duration_seconds: float | None = None