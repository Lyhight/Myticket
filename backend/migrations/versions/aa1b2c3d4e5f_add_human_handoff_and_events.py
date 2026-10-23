"""add human handoff ownership and durable domain events

Revision ID: aa1b2c3d4e5f
Revises: f4a5b6c7d8e9
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "aa1b2c3d4e5f"
down_revision: Union[str, None] = "f4a5b6c7d8e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tickets", sa.Column("assigned_agent_id", sa.Integer(), nullable=True))
    op.add_column("tickets", sa.Column("escalation_reason", sa.String(500), nullable=True))
    op.add_column("tickets", sa.Column("claimed_at", sa.DateTime(), nullable=True))
    op.add_column("tickets", sa.Column("human_started_at", sa.DateTime(), nullable=True))
    op.add_column("tickets", sa.Column("resolved_at", sa.DateTime(), nullable=True))
    op.create_foreign_key(
        "fk_tickets_assigned_agent_users",
        "tickets", "users", ["assigned_agent_id"], ["id"],
    )
    op.create_index("ix_tickets_assigned_agent_id", "tickets", ["assigned_agent_id"])
    op.create_index("ix_tickets_status_created_at", "tickets", ["status", "created_at"])
    op.create_index("ix_tickets_agent_status", "tickets", ["assigned_agent_id", "status"])
    op.create_table(
        "domain_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("aggregate_type", sa.String(50), nullable=False),
        sa.Column("aggregate_id", sa.Integer(), nullable=False),
        sa.Column("audience_role", sa.String(50), nullable=True),
        sa.Column("audience_user_id", sa.Integer(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in (
        ("ix_domain_events_event_type", ["event_type"]),
        ("ix_domain_events_aggregate_id", ["aggregate_id"]),
        ("ix_domain_events_audience_role", ["audience_role"]),
        ("ix_domain_events_audience_user_id", ["audience_user_id"]),
        ("ix_domain_events_created_at", ["created_at"]),
    ):
        op.create_index(name, "domain_events", columns)


def downgrade() -> None:
    op.drop_table("domain_events")
    op.drop_index("ix_tickets_agent_status", table_name="tickets")
    op.drop_index("ix_tickets_status_created_at", table_name="tickets")
    op.drop_constraint("fk_tickets_assigned_agent_users", "tickets", type_="foreignkey")
    op.drop_index("ix_tickets_assigned_agent_id", table_name="tickets")
    for column in (
        "resolved_at", "human_started_at", "claimed_at",
        "escalation_reason", "assigned_agent_id",
    ):
        op.drop_column("tickets", column)
