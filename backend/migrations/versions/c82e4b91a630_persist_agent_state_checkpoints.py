"""persist agent state checkpoints

Revision ID: c82e4b91a630
Revises: b7d3a6e41f20
Create Date: 2026-09-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c82e4b91a630"
down_revision: Union[str, Sequence[str], None] = "b7d3a6e41f20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column(
            "state_snapshot",
            sa.JSON(),
            nullable=True,
        ),
    )
    op.add_column(
        "agent_runs",
        sa.Column(
            "checkpoint_status",
            sa.String(length=50),
            nullable=True,
        ),
    )
    op.create_index(
        op.f("ix_agent_runs_checkpoint_status"),
        "agent_runs",
        ["checkpoint_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_agent_runs_checkpoint_status"),
        table_name="agent_runs",
    )
    op.drop_column("agent_runs", "checkpoint_status")
    op.drop_column("agent_runs", "state_snapshot")
