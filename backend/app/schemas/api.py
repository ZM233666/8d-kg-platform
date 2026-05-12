"""API 请求/响应 Pydantic 模型（不复用 ORM 模型，避免暴露内部字段）。"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DocumentResponse(BaseModel):
    id: UUID
    filename: str
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


class ExtractionTriggerResponse(BaseModel):
    run_id: UUID
    document_id: UUID
    status: str
    message: str = "extraction completed synchronously (Celery integration deferred to batch 6C)"
