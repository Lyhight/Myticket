from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    ticket_id: Mapped[int] = mapped_column(
        ForeignKey("tickets.id"),
        nullable=False,
        index=True,
    )
    correlation_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
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

    action: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    action_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    tool_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    tool_args: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )

    tool_result: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )

    final_reply: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    review_approved: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )

    review_issues: Mapped[list[str] | None] = mapped_column(
        JSON,
        nullable=True,
    )

    state_snapshot: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )

    checkpoint_status: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )

    rag_trace: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )
    memory_trace: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )
    context_trace: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )
    total_latency_ms: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    model_provider: Mapped[str | None] = mapped_column(
        String(30), nullable=True
    )
    model_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    prompt_versions: Mapped[dict[str, str] | None] = mapped_column(
        JSON, nullable=True
    )
    token_usage: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )
