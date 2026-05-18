"""API 请求/响应 Pydantic 模型（不复用 ORM 模型，避免暴露内部字段）。"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DocumentResponse(BaseModel):
    id: UUID
    file_name: str
    file_size: int
    mime_type: str
    sha256: str
    minio_key: str
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UploadResponse(BaseModel):
    document: DocumentResponse
    already_exists: bool = Field(description="True 表示 sha256 命中已有文档")


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int
    offset: int
    limit: int


class ExtractionRunResponse(BaseModel):
    id: UUID
    document_id: UUID
    document_file_name: str | None = Field(
        default=None,
        description="关联文档文件名（来自 documents.file_name）",
    )
    pipeline_version: str
    llm_model: str | None
    status: str
    started_at: datetime
    finished_at: datetime | None
    token_input: int | None
    token_output: int | None
    cost_estimate: float | None
    stage_metrics: dict | None
    error_detail: dict | None

    model_config = ConfigDict(from_attributes=True)


class ExtractionRunListResponse(BaseModel):
    items: list[ExtractionRunResponse]
    total: int
    offset: int
    limit: int


class ExtractionCancelResponse(BaseModel):
    run_id: UUID
    status: str
    cancelled: bool = True
    message: str = "extraction cancelled"


class ExtractionTriggerResponse(BaseModel):
    run_id: UUID
    document_id: UUID
    status: str
    message: str = "extraction completed synchronously (Celery integration deferred to batch 6C)"


class SubgraphNode(BaseModel):
    business_key: str | None
    labels: list[str]
    properties: dict


class SubgraphRelationship(BaseModel):
    type: str
    start_bk: str | None
    start_label: str | None
    end_bk: str | None
    end_label: str | None
    properties: dict


class SubgraphResponse(BaseModel):
    center: dict  # {"business_key": ..., "label": ...}
    depth: int
    nodes: list[SubgraphNode]
    relationships: list[SubgraphRelationship]
    stats: dict  # {"node_count": int, "relationship_count": int}