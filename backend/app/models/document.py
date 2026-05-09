"""Document 模型（8D 报告原始文档元数据）。"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import DocumentStatus


class Document(Base, UUIDPKMixin, TimestampMixin):
    """原始上传文档的元数据表。

    FK: 无（其他表通过 document_id 引用本表）。
    """

    __tablename__ = "documents"

    # 文件元数据
    file_name: Mapped[str] = mapped_column(String(512), nullable=False)
    file_size: Mapped[int] = mapped_column(nullable=False)
    mime_type: Mapped[str] = mapped_column(String(64), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

    # MinIO 存储
    minio_key: Mapped[str] = mapped_column(String(512), nullable=False)

    # 上传者
    upload_user_id: Mapped[UUID] = mapped_column(nullable=False)

    # 状态
    status: Mapped[DocumentStatus] = mapped_column(
        String(32),
        nullable=False,
        default=DocumentStatus.UPLOADED,
        server_default=DocumentStatus.UPLOADED.value,
        index=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
