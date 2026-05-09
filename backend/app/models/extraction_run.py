"""ExtractionRun 模型（pipeline 每次运行的记录）。"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import ExtractionRunStatus


class ExtractionRun(Base, UUIDPKMixin, TimestampMixin):
    """Pipeline 每次运行的记录表。

    FK: document_id → documents(id)。
    选择 ON DELETE CASCADE：文档删除时级联删除其所有 run 记录。

    时间字段语义：created_at=入库时间, started_at=Worker 拾起任务的时间, finished_at=结束时间。
    """

    __tablename__ = "extraction_runs"

    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    pipeline_version: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pipeline-v0.1.0",
    )
    llm_model: Mapped[str | None] = mapped_column(String(64), nullable=True)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # 状态：pending / running / succeeded / failed
    status: Mapped[ExtractionRunStatus] = mapped_column(
        String(32),
        nullable=False,
        default=ExtractionRunStatus.PENDING,
        index=True,
    )

    # stage 执行指标（JSONB，存储各 stage 的 duration_ms / items_processed 等）
    stage_metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # LLM 计量
    token_input: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_output: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_estimate: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)

    # 错误详情
    error_detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # trace_id（关联日志链路）
    trace_id: Mapped[UUID | None] = mapped_column(nullable=True)

    __table_args__ = (
        Index("ix_extraction_runs_document_started", "document_id", "started_at"),
    )
