"""Chunk 模型（按章节切分的文本块）。"""

from uuid import UUID

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class Chunk(Base, UUIDPKMixin, TimestampMixin):
    """文档切分后的原文片段表。

    FK: document_id → documents(id)。
    选择 ON DELETE CASCADE：文档删除时自动清理其所有 chunk。
    """

    __tablename__ = "chunks"

    # 关联文档
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )

    # 切分信息
    chunk_index: Mapped[int] = mapped_column(nullable=False)
    chunk_business_key: Mapped[str] = mapped_column(
        String(512),
        unique=True,
        index=True,
        nullable=False,
    )
    chapter_path: Mapped[list[str]] = mapped_column(
        ARRAY(String),
        nullable=False,
        default=list,
    )

    # 文本内容
    text: Mapped[str] = mapped_column(Text, nullable=False)

    # 统计
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # 标签
    chunk_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_table: Mapped[bool] = mapped_column(default=False)
    table_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_placeholder: Mapped[bool] = mapped_column(default=False)
    has_referenced_image: Mapped[bool] = mapped_column(default=False)

    # 向量（v0.2 启用）
    # v0.1 不存 embedding；v0.2 接入 pgvector 时通过 alembic 迁移新增 embedding vector(1024) 列。

    # 唯一约束 + 索引
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_chunks_document_chunk_index"),
        Index("ix_chunks_document_id", "document_id"),
    )
