"""create refund requests table

Revision ID: a51c9f2d1e70
Revises: 9b03c403ff90
Create Date: 2026-09-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a51c9f2d1e70"
down_revision: Union[str, Sequence[str], None] = "9b03c403ff90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "refund_requests",
        sa.Column(
            "id",
            sa.Integer(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "request_no",
            sa.String(length=50),
            nullable=False,
        ),
        sa.Column(
            "order_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "idempotency_key",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
        ),
        sa.Column(
            "reason",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "amount",
            sa.Float(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_refund_requests_request_no"),
        "refund_requests",
        ["request_no"],
        unique=True,
    )
    op.create_index(
        op.f("ix_refund_requests_order_id"),
        "refund_requests",
        ["order_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_refund_requests_idempotency_key"),
        "refund_requests",
        ["idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_refund_requests_idempotency_key"),
        table_name="refund_requests",
    )
    op.drop_index(
        op.f("ix_refund_requests_order_id"),
        table_name="refund_requests",
    )
    op.drop_index(
        op.f("ix_refund_requests_request_no"),
        table_name="refund_requests",
    )
    op.drop_table("refund_requests")
