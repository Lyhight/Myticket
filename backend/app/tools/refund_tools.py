from typing import Any

from app.db.session import AsyncSessionLocal
from app.models.order import Order
from app.repositories.order_repository import OrderRepository
from app.repositories.refund_repository import (
    RefundRequestRepository,
)


def assess_refund_eligibility(
    order: Order,
) -> dict[str, Any]:
    if order.status == "REFUNDED":
        return {
            "eligible": False,
            "requires_human": False,
            "reason": "ORDER_ALREADY_REFUNDED",
        }

    if order.status == "CANCELLED":
        return {
            "eligible": False,
            "requires_human": False,
            "reason": "ORDER_ALREADY_CANCELLED",
        }

    if (
        order.status == "PAID"
        and order.shipping_status == "NOT_SHIPPED"
    ):
        return {
            "eligible": True,
            "requires_human": False,
            "reason": "PAID_ORDER_NOT_SHIPPED",
        }

    return {
        "eligible": False,
        "requires_human": True,
        "reason": "ORDER_REQUIRES_AFTER_SALES_REVIEW",
    }


async def check_refund_eligibility(
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
        }

    assessment = assess_refund_eligibility(order)

    return {
        "success": True,
        "order_id": order.order_no,
        "amount": order.amount,
        **assessment,
    }


async def create_refund_request(
    order_id: str,
    reason: str,
    idempotency_key: str,
    user_id: int,
    confirmed: bool = False,
    human_approved: bool = False,
) -> dict[str, Any]:
    if not confirmed:
        return {
            "success": False,
            "error": "CONFIRMATION_REQUIRED",
            "message": "创建退款申请前需要用户明确确认。",
        }

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
            }

        assessment = assess_refund_eligibility(order)

        if (
            not assessment["eligible"]
            and not (
                human_approved
                and assessment["requires_human"]
            )
        ):
            return {
                "success": False,
                "error": "REFUND_NOT_ELIGIBLE",
                **assessment,
            }

        refund, created = await RefundRequestRepository(
            db
        ).create(
            order_id=order.id,
            reason=reason,
            amount=order.amount,
            idempotency_key=idempotency_key,
        )

    return {
        "success": True,
        "created": created,
        "refund": {
            "request_no": refund.request_no,
            "order_id": order.order_no,
            "status": refund.status,
            "amount": refund.amount,
        },
    }
