from typing import Any

from app.db.session import AsyncSessionLocal
from app.repositories.logistics_repository import (
    LogisticsRepository,
)


async def get_logistics(
    tracking_number: str,
    user_id: int,
) -> dict[str, Any]:

    async with AsyncSessionLocal() as db:
        logistics = await LogisticsRepository(
            db
        ).get_by_tracking_number_for_user(
            tracking_number,
            user_id,
        )

    if logistics is None:
        return {
            "success": False,
            "error": "LOGISTICS_NOT_FOUND",
            "message": (
                f"未找到物流单号 "
                f"{tracking_number}"
            ),
        }

    return {
        "success": True,
        "logistics": {
            "tracking_number": logistics.tracking_number,
            "carrier": logistics.carrier,
            "status": logistics.status,
            "current_location": logistics.current_location,
            "estimated_delivery": (
                logistics.estimated_delivery.isoformat()
                if logistics.estimated_delivery
                else None
            ),
        },
    }
