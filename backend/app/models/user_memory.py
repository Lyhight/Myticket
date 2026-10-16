from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserMemory(Base):
    __tablename__ = "user_memories"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "fingerprint",
            name="uq_user_memories_user_fingerprint",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    memory_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    fingerprint: Mapped[str] = mapped_column(
        String(64), nullable=False
    )
    memory_key: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    confidence: Mapped[float] = mapped_column(
        Float, default=1.0, nullable=False
    )
    source_ticket_id: Mapped[int | None] = mapped_column(
        ForeignKey("tickets.id"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, index=True
    )
    last_accessed_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
