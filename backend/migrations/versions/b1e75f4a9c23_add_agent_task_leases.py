"""add worker leases and heartbeat to agent tasks

Revision ID: b1e75f4a9c23
Revises: a0d64e3f8b12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b1e75f4a9c23"
down_revision: Union[str, None] = "a0d64e3f8b12"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agent_tasks", sa.Column("locked_by", sa.String(100), nullable=True))
    op.add_column("agent_tasks", sa.Column("lease_expires_at", sa.DateTime(), nullable=True))
    op.add_column("agent_tasks", sa.Column("heartbeat_at", sa.DateTime(), nullable=True))
    op.create_index("ix_agent_tasks_locked_by", "agent_tasks", ["locked_by"])
    op.create_index("ix_agent_tasks_lease_expires_at", "agent_tasks", ["lease_expires_at"])


def downgrade() -> None:
    op.drop_index("ix_agent_tasks_lease_expires_at", table_name="agent_tasks")
    op.drop_index("ix_agent_tasks_locked_by", table_name="agent_tasks")
    op.drop_column("agent_tasks", "heartbeat_at")
    op.drop_column("agent_tasks", "lease_expires_at")
    op.drop_column("agent_tasks", "locked_by")
