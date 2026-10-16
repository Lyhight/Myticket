"""add agent observability traces

Revision ID: b31f7d28e904
Revises: a92e6f14c830
Create Date: 2026-10-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b31f7d28e904"
down_revision: Union[str, Sequence[str], None] = "a92e6f14c830"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("rag_trace", sa.JSON(), nullable=True))
    op.add_column("agent_runs", sa.Column("memory_trace", sa.JSON(), nullable=True))
    op.add_column("agent_runs", sa.Column("context_trace", sa.JSON(), nullable=True))
    op.add_column("agent_runs", sa.Column("total_latency_ms", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_runs", "total_latency_ms")
    op.drop_column("agent_runs", "context_trace")
    op.drop_column("agent_runs", "memory_trace")
    op.drop_column("agent_runs", "rag_trace")
