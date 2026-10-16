"""add ticket optimistic concurrency version

Revision ID: d7a91f3c2b40
Revises: b31f7d28e904
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d7a91f3c2b40"
down_revision: Union[str, None] = "b31f7d28e904"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tickets",
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("tickets", "version")
