"""add embeddings to knowledge chunks

Revision ID: a92e6f14c830
Revises: f7c2d8a41b65
Create Date: 2026-10-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a92e6f14c830"
down_revision: Union[str, Sequence[str], None] = "f7c2d8a41b65"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "knowledge_chunks",
        sa.Column("embedding", sa.JSON(), nullable=True),
    )
    op.add_column(
        "knowledge_chunks",
        sa.Column("embedding_model", sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("knowledge_chunks", "embedding_model")
    op.drop_column("knowledge_chunks", "embedding")
