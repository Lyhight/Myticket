"""为本地演示创建用户、订单和物流数据。

用法:
    .venv/Scripts/python.exe seed_demo_data.py

脚本幂等：可以重复运行，不会创建重复数据。
已经属于其他用户的订单不会被重新绑定。
"""
import asyncio
import json
import os
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.models.logistics import Logistics
from app.models.order import Order
from app.models.user import User


DEMO_USER_EMAIL = os.getenv(
    "DEMO_USER_EMAIL",
    "demo@example.com",
)
DEMO_USER_PASSWORD = os.getenv(
    "DEMO_USER_PASSWORD",
    "DemoPass123!",
)
DEMO_ADMIN_EMAIL = os.getenv(
    "DEMO_ADMIN_EMAIL",
    "admin@example.com",
)
DEMO_ADMIN_PASSWORD = os.getenv(
    "DEMO_ADMIN_PASSWORD",
    "AdminPass123!",
)

SYNTHETIC_ORDER_PATH = (
    Path(__file__).parent.parent / "synthetic_data" / "orders" / "orders.json"
)


def load_demo_business_data(
    path: Path = SYNTHETIC_ORDER_PATH,
) -> tuple[list[dict], list[dict]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    orders: list[dict] = []
    logistics_items: list[dict] = []
    for item in payload["orders"]:
        orders.append({
            key: item[key]
            for key in (
                "order_no",
                "status",
                "shipping_status",
                "product_name",
                "amount",
            )
        })
        logistics = item.get("logistics")
        if logistics:
            logistics = dict(logistics)
            if logistics.get("estimated_delivery"):
                logistics["estimated_delivery"] = date.fromisoformat(
                    logistics["estimated_delivery"]
                )
            logistics_items.append(logistics)
    return orders, logistics_items


ORDERS, LOGISTICS = load_demo_business_data()


async def get_or_create_demo_user(
    db: AsyncSession,
) -> tuple[User, bool]:
    result = await db.execute(
        select(User).where(User.email == DEMO_USER_EMAIL)
    )
    user = result.scalar_one_or_none()

    if user is not None:
        return user, False

    user = User(
        email=DEMO_USER_EMAIL,
        password_hash=hash_password(DEMO_USER_PASSWORD),
        role="customer",
        is_active=True,
    )
    db.add(user)
    await db.flush()
    return user, True


async def get_or_create_demo_admin(
    db: AsyncSession,
) -> tuple[User, bool]:
    result = await db.execute(
        select(User).where(User.email == DEMO_ADMIN_EMAIL)
    )
    user = result.scalar_one_or_none()
    if user is not None:
        return user, False
    user = User(
        email=DEMO_ADMIN_EMAIL,
        password_hash=hash_password(DEMO_ADMIN_PASSWORD),
        role="admin",
        is_active=True,
    )
    db.add(user)
    await db.flush()
    return user, True


async def seed_database(
    db: AsyncSession,
) -> dict[str, int]:
    demo_user, user_created = await get_or_create_demo_user(db)
    _, admin_created = await get_or_create_demo_admin(db)
    stats = {
        "users_created": int(user_created) + int(admin_created),
        "customers_created": int(user_created),
        "admins_created": int(admin_created),
        "orders_created": 0,
        "orders_assigned": 0,
        "orders_preserved": 0,
        "logistics_created": 0,
        "logistics_assigned": 0,
        "logistics_preserved": 0,
    }

    for item in ORDERS:
        result = await db.execute(
            select(Order).where(Order.order_no == item["order_no"])
        )
        order = result.scalar_one_or_none()

        if order is None:
            db.add(Order(**item, user_id=demo_user.id))
            stats["orders_created"] += 1
        elif order.user_id is None:
            order.user_id = demo_user.id
            stats["orders_assigned"] += 1
        elif order.user_id != demo_user.id:
            # 不覆盖已经明确属于其他用户的订单。
            stats["orders_preserved"] += 1

    for item in LOGISTICS:
        result = await db.execute(
            select(Logistics).where(
                Logistics.tracking_number == item["tracking_number"]
            )
        )

        logistics = result.scalar_one_or_none()
        if logistics is None:
            db.add(Logistics(**item, user_id=demo_user.id))
            stats["logistics_created"] += 1
        elif logistics.user_id is None:
            logistics.user_id = demo_user.id
            stats["logistics_assigned"] += 1
        elif logistics.user_id != demo_user.id:
            stats["logistics_preserved"] += 1

    await db.commit()
    return stats


async def seed() -> None:
    async with AsyncSessionLocal() as db:
        stats = await seed_database(db)

    print("Seeding done.")
    print(f"Demo user: {DEMO_USER_EMAIL}")
    print(f"Demo admin: {DEMO_ADMIN_EMAIL}")
    print("Password: value of DEMO_USER_PASSWORD")
    print(f"Summary: {stats}")


if __name__ == "__main__":
    asyncio.run(seed())
