"""add user ownership to orders

Revision ID: b7d3a6e41f20
Revises: a51c9f2d1e70
Create Date: 2026-09-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7d3a6e41f20"
down_revision: Union[str, Sequence[str], None] = "a51c9f2d1e70"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column(
            "user_id",
            sa.Integer(),
            nullable=True,
        ),
    )
    op.create_index(
        op.f("ix_orders_user_id"),
        "orders",
        ["user_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_orders_user_id_users",
        "orders",
        "users",
        ["user_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_orders_user_id_users",
        "orders",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_orders_user_id"),
        table_name="orders",
    )
    op.drop_column("orders", "user_id")
