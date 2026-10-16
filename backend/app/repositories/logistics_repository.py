from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.logistics import Logistics


class LogisticsRepository:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_tracking_number(
        self,
        tracking_number: str,
    ) -> Logistics | None:
        """
        根据物流单号查询物流信息。
        """

        result = await self.db.execute(
            select(Logistics).where(
                Logistics.tracking_number == tracking_number
            )
        )

        return result.scalar_one_or_none()

    async def get_by_tracking_number_for_user(
        self,
        tracking_number: str,
        user_id: int,
    ) -> Logistics | None:
        result = await self.db.execute(
            select(Logistics).where(
                Logistics.tracking_number == tracking_number,
                Logistics.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()
