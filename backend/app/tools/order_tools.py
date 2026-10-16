from typing import Any

from app.db.session import AsyncSessionLocal
from app.repositories.order_repository import OrderRepository


async def get_order(
    order_id: str,
    user_id: int,
) -> dict[str, Any]:

    async with AsyncSessionLocal() as db:
        order = await OrderRepository(
            db
        ).get_by_order_no_for_user(
            order_id,
            user_id,
        )

    if order is None:
        return {
            "success": False,
            "error": "ORDER_NOT_FOUND",
            "message": (
                f"Order {order_id} "
                "was not found."
            ),
        }

    return {
        "success": True,
        "order": {
            "order_id": order.order_no,
            "status": order.status,
            "shipping_status": order.shipping_status,
            "product_name": order.product_name,
            "amount": order.amount,
        },
    }
