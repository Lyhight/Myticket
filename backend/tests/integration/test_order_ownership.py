from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.order import Order
from app.models.logistics import Logistics
from app.repositories.logistics_repository import LogisticsRepository
from app.models.user import User
from app.repositories.order_repository import OrderRepository


async def create_user(
    db_session: AsyncSession,
    email: str,
) -> User:
    user = User(
        email=email,
        password_hash=hash_password("test-password"),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def test_order_can_be_loaded_by_owner(
    db_session: AsyncSession,
) -> None:
    owner = await create_user(
        db_session,
        "owner@example.com",
    )
    order = Order(
        user_id=owner.id,
        order_no="OWNER-10001",
        status="PAID",
        shipping_status="NOT_SHIPPED",
        product_name="无线耳机",
        amount=299,
    )
    db_session.add(order)
    await db_session.commit()

    result = await OrderRepository(
        db_session
    ).get_by_order_no_for_user(
        "OWNER-10001",
        owner.id,
    )

    assert result is not None
    assert result.user_id == owner.id


async def test_other_user_cannot_load_order(
    db_session: AsyncSession,
) -> None:
    owner = await create_user(
        db_session,
        "owner@example.com",
    )
    other = await create_user(
        db_session,
        "other@example.com",
    )
    order = Order(
        user_id=owner.id,
        order_no="OWNER-10002",
        status="PAID",
        shipping_status="NOT_SHIPPED",
        product_name="机械键盘",
        amount=499,
    )
    db_session.add(order)
    await db_session.commit()

    result = await OrderRepository(
        db_session
    ).get_by_order_no_for_user(
        "OWNER-10002",
        other.id,
    )

    assert result is None


async def test_legacy_unowned_order_is_not_user_accessible(
    db_session: AsyncSession,
) -> None:
    user = await create_user(
        db_session,
        "customer@example.com",
    )
    order = Order(
        user_id=None,
        order_no="LEGACY-10001",
        status="PAID",
        shipping_status="NOT_SHIPPED",
        product_name="历史订单",
        amount=99,
    )
    db_session.add(order)
    await db_session.commit()

    result = await OrderRepository(
        db_session
    ).get_by_order_no_for_user(
        "LEGACY-10001",
        user.id,
    )

    assert result is None


async def test_logistics_is_only_visible_to_its_owner(
    db_session: AsyncSession,
) -> None:
    owner = await create_user(db_session, "logistics-owner@example.com")
    other = await create_user(db_session, "logistics-other@example.com")
    logistics = Logistics(
        user_id=owner.id,
        tracking_number="PRIVATE-SF-001",
        carrier="顺丰",
        status="IN_TRANSIT",
    )
    db_session.add(logistics)
    await db_session.commit()
    repository = LogisticsRepository(db_session)

    assert await repository.get_by_tracking_number_for_user(
        "PRIVATE-SF-001", owner.id
    ) is not None
    assert await repository.get_by_tracking_number_for_user(
        "PRIVATE-SF-001", other.id
    ) is None
