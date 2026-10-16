from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.logistics import Logistics
from app.models.order import Order
from app.models.user import User
from seed_demo_data import DEMO_USER_EMAIL, ORDERS, seed_database


async def test_seed_creates_owned_demo_data(
    db_session: AsyncSession,
) -> None:
    stats = await seed_database(db_session)

    user = (
        await db_session.execute(
            select(User).where(User.email == DEMO_USER_EMAIL)
        )
    ).scalar_one()
    orders = list(
        (
            await db_session.execute(
                select(Order).order_by(Order.order_no)
            )
        ).scalars()
    )

    assert stats["users_created"] == 2
    assert stats["orders_created"] == len(ORDERS)
    assert all(order.user_id == user.id for order in orders)
    logistics = list(
        (await db_session.execute(select(Logistics))).scalars()
    )
    assert all(item.user_id == user.id for item in logistics)


async def test_seed_is_idempotent(
    db_session: AsyncSession,
) -> None:
    await seed_database(db_session)
    second_stats = await seed_database(db_session)

    user_count = await db_session.scalar(
        select(func.count()).select_from(User)
    )
    order_count = await db_session.scalar(
        select(func.count()).select_from(Order)
    )
    logistics_count = await db_session.scalar(
        select(func.count()).select_from(Logistics)
    )

    assert user_count == 2
    assert order_count == 5
    assert logistics_count == 3
    assert second_stats["users_created"] == 0
    assert second_stats["orders_created"] == 0
    assert second_stats["orders_assigned"] == 0
    assert second_stats["logistics_created"] == 0
    assert second_stats["logistics_assigned"] == 0


async def test_seed_does_not_reassign_an_owned_order(
    db_session: AsyncSession,
) -> None:
    other_user = User(
        email="owner@example.com",
        password_hash="not-used-in-this-test",
    )
    db_session.add(other_user)
    await db_session.flush()

    existing_order = Order(
        user_id=other_user.id,
        **ORDERS[0],
    )
    db_session.add(existing_order)
    await db_session.commit()

    stats = await seed_database(db_session)
    await db_session.refresh(existing_order)

    assert existing_order.user_id == other_user.id
    assert stats["orders_preserved"] == 1
