"""add database-level active refund order key

Revision ID: e8b42c1d6f90
Revises: d7a91f3c2b40
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e8b42c1d6f90"
down_revision: Union[str, None] = "d7a91f3c2b40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "refund_requests",
        sa.Column("active_order_key", sa.String(100), nullable=True),
    )
    # 兼容已有数据：每个订单只把最早的一条活跃申请标为有效键，
    # 避免历史重复数据导致唯一约束迁移失败。
    op.execute(
        """
        UPDATE refund_requests AS r
        JOIN (
            SELECT order_id, MIN(id) AS keep_id
            FROM refund_requests
            WHERE status IN ('PENDING', 'PROCESSING')
            GROUP BY order_id
        ) AS active ON active.keep_id = r.id
        SET r.active_order_key = CONCAT('order:', r.order_id)
        """
    )
    op.create_unique_constraint(
        "uq_refund_requests_active_order_key",
        "refund_requests",
        ["active_order_key"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_refund_requests_active_order_key",
        "refund_requests",
        type_="unique",
    )
    op.drop_column("refund_requests", "active_order_key")
