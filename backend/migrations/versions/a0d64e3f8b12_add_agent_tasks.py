"""add durable agent tasks and idempotent messages

Revision ID: a0d64e3f8b12
Revises: f9c53d2e7a01
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a0d64e3f8b12"
down_revision: Union[str, None] = "f9c53d2e7a01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("operation_key", sa.String(180), nullable=True),
    )
    op.create_index(
        "ix_messages_operation_key",
        "messages",
        ["operation_key"],
        unique=True,
    )
    op.create_table(
        "agent_tasks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("task_type", sa.String(50), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("next_retry_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("result_message_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["result_message_id"], ["messages.id"]),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    for column in ("idempotency_key", "ticket_id", "user_id", "status", "next_retry_at"):
        op.create_index(f"ix_agent_tasks_{column}", "agent_tasks", [column])


def downgrade() -> None:
    op.drop_table("agent_tasks")
    op.drop_index("ix_messages_operation_key", table_name="messages")
    op.drop_column("messages", "operation_key")
