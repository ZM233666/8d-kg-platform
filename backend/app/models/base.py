"""SQLAlchemy ORM 基类：Base / TimestampMixin / UUIDPKMixin。"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, String, func, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """所有 ORM 模型的单一基类。"""

    type_annotation_map = {
        UUID: PG_UUID(as_uuid=True),
        str: String(),
    }


class UUIDPKMixin:
    """主键为 UUID 的混入类，使用 PG gen_random_uuid() 生成。"""

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )


class TimestampMixin:
    """自动填充 created_at / updated_at 的混入类。"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=datetime.utcnow,
    )
