from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order


class OrderRepository:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_order_no(
        self,
        order_no: str,
    ) -> Order | None:
        """
        根据业务订单号查询订单。
        """

        result = await self.db.execute(
            select(Order).where(
                Order.order_no == order_no
            )
        )

        return result.scalar_one_or_none()

    async def get_by_order_no_for_user(
        self,
        order_no: str,
        user_id: int,
    ) -> Order | None:
        """查询属于指定用户的订单，避免跨用户访问。"""

        result = await self.db.execute(
            select(Order).where(
                Order.order_no == order_no,
                Order.user_id == user_id,
            )
        )

        return result.scalar_one_or_none()
