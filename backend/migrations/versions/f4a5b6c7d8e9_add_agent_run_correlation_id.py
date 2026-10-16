"""add agent run correlation id

Revision ID: f4a5b6c7d8e9
Revises: d3f4a5b6c7d8
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f4a5b6c7d8e9"
down_revision: Union[str, None] = "d3f4a5b6c7d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        op.f("ix_agent_runs_correlation_id"),
        "agent_runs",
        ["correlation_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_agent_runs_correlation_id"),
        table_name="agent_runs",
    )
    op.drop_column("agent_runs", "correlation_id")
