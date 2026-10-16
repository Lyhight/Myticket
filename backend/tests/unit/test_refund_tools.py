from types import SimpleNamespace

import pytest

from app.tools import tool_registry
from app.tools.refund_tools import (
    assess_refund_eligibility,
    create_refund_request,
)


def test_paid_unshipped_order_is_eligible() -> None:
    order = SimpleNamespace(
        status="PAID",
        shipping_status="NOT_SHIPPED",
    )

    result = assess_refund_eligibility(order)

    assert result == {
        "eligible": True,
        "requires_human": False,
        "reason": "PAID_ORDER_NOT_SHIPPED",
    }


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        ("REFUNDED", "ORDER_ALREADY_REFUNDED"),
        ("CANCELLED", "ORDER_ALREADY_CANCELLED"),
    ],
)
def test_finished_order_is_not_eligible(
    status: str,
    reason: str,
) -> None:
    order = SimpleNamespace(
        status=status,
        shipping_status="NOT_SHIPPED",
    )

    result = assess_refund_eligibility(order)

    assert result["eligible"] is False
    assert result["requires_human"] is False
    assert result["reason"] == reason


def test_shipped_order_requires_human_review() -> None:
    order = SimpleNamespace(
        status="SHIPPED",
        shipping_status="IN_TRANSIT",
    )

    result = assess_refund_eligibility(order)

    assert result["eligible"] is False
    assert result["requires_human"] is True
    assert result["reason"] == (
        "ORDER_REQUIRES_AFTER_SALES_REVIEW"
    )


async def test_create_refund_requires_confirmation() -> None:
    result = await create_refund_request(
        order_id="10001",
        reason="不再需要",
        idempotency_key="ticket-1-refund",
        user_id=1,
        confirmed=False,
    )

    assert result["success"] is False
    assert result["error"] == "CONFIRMATION_REQUIRED"


def test_refund_tools_are_registered() -> None:
    assert tool_registry.exists(
        "check_refund_eligibility"
    )
    assert tool_registry.exists(
        "create_refund_request"
    )
