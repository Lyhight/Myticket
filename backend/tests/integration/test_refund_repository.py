from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order
from app.models.refund import RefundRequest
from app.repositories.refund_repository import (
    RefundRequestRepository,
)


async def test_refund_creation_is_idempotent(
    db_session: AsyncSession,
) -> None:
    order = Order(
        order_no="10001",
        status="PAID",
        shipping_status="NOT_SHIPPED",
        product_name="无线耳机",
        amount=299,
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)

    repository = RefundRequestRepository(db_session)

    first, first_created = await repository.create(
        order_id=order.id,
        reason="不再需要",
        amount=order.amount,
        idempotency_key="ticket-1-refund",
    )
    second, second_created = await repository.create(
        order_id=order.id,
        reason="重复请求不应新建",
        amount=order.amount,
        idempotency_key="ticket-1-refund",
    )

    assert first_created is True
    assert second_created is False
    assert second.id == first.id
    assert second.request_no == first.request_no

    result = await db_session.execute(
        select(RefundRequest)
    )
    assert len(result.scalars().all()) == 1


async def test_refund_can_be_found_by_request_number(
    db_session: AsyncSession,
) -> None:
    order = Order(
        order_no="10002",
        status="PAID",
        shipping_status="NOT_SHIPPED",
        product_name="机械键盘",
        amount=499,
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)

    repository = RefundRequestRepository(db_session)
    refund, _ = await repository.create(
        order_id=order.id,
        reason="商品不合适",
        amount=order.amount,
        idempotency_key="ticket-2-refund",
    )

    found = await repository.get_by_request_no(
        refund.request_no
    )

    assert found is not None
    assert found.id == refund.id
    assert found.status == "PENDING"


async def test_same_order_with_different_key_is_idempotent(
    db_session: AsyncSession,
) -> None:
    order = Order(
        order_no="10003",
        status="PAID",
        shipping_status="NOT_SHIPPED",
        product_name="显示器",
        amount=1599,
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)
    repository = RefundRequestRepository(db_session)

    first, first_created = await repository.create(
        order_id=order.id,
        reason="第一次申请",
        amount=order.amount,
        idempotency_key="ticket-a-refund",
    )
    second, second_created = await repository.create(
        order_id=order.id,
        reason="另一个工单重复申请",
        amount=order.amount,
        idempotency_key="ticket-b-refund",
    )

    assert first_created is True
    assert second_created is False
    assert second.id == first.id
