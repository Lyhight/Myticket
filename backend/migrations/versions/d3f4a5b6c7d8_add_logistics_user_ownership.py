"""add user ownership to logistics

Revision ID: d3f4a5b6c7d8
Revises: c2f86a5b0d34
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d3f4a5b6c7d8"
down_revision: Union[str, None] = "c2f86a5b0d34"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "logistics",
        sa.Column("user_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        op.f("ix_logistics_user_id"),
        "logistics",
        ["user_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_logistics_user_id_users",
        "logistics",
        "users",
        ["user_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_logistics_user_id_users",
        "logistics",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_logistics_user_id"),
        table_name="logistics",
    )
    op.drop_column("logistics", "user_id")
