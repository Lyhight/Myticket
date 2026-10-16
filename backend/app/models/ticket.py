from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    category: Mapped[str] = mapped_column(
        String(50),
        default="OTHER",
        nullable=False,
    )

    priority: Mapped[str] = mapped_column(
        String(20),
        default="NORMAL",
        nullable=False,
    )

    intent: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    route_to: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="OPEN",
        nullable=False,
    )

    # 乐观并发版本。每次开始处理一条新消息时原子递增，
    # 防止两个进程同时从同一个旧 checkpoint 继续执行。
    version: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="ticket",
        cascade="all, delete-orphan",
    )
    classification_source: Mapped[str | None] = mapped_column(
    String(30),
    nullable=True,
    )

    classification_attempts: Mapped[int | None] = mapped_column(
    Integer,
    nullable=True,
    )

    classification_latency_ms: Mapped[float | None] = mapped_column(
    Float,
    nullable=True,
    )

    classification_fallback_used: Mapped[bool] = mapped_column(
    Boolean,
    default=False,
    nullable=False,
    )

    classified_at: Mapped[datetime | None] = mapped_column(
    DateTime,
    nullable=True,
    )
