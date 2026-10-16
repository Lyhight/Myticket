"""add model prompt versions and token telemetry to agent runs

Revision ID: c2f86a5b0d34
Revises: b1e75f4a9c23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c2f86a5b0d34"
down_revision: Union[str, None] = "b1e75f4a9c23"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("model_provider", sa.String(30), nullable=True))
    op.add_column("agent_runs", sa.Column("model_name", sa.String(100), nullable=True))
    op.add_column("agent_runs", sa.Column("prompt_versions", sa.JSON(), nullable=True))
    op.add_column("agent_runs", sa.Column("token_usage", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_runs", "token_usage")
    op.drop_column("agent_runs", "prompt_versions")
    op.drop_column("agent_runs", "model_name")
    op.drop_column("agent_runs", "model_provider")
