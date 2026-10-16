import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.agent.schemas import (
    ClassificationExecution,
    TicketClassification,
)
from app.agent.service import TicketClassificationService
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.order import Order
from app.models.refund import RefundRequest
from app.models.user import User


@pytest_asyncio.fixture
async def refund_client(
    monkeypatch: pytest.MonkeyPatch,
):
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        user = User(
            email="refund-e2e@example.com",
            password_hash=hash_password("strong-password"),
        )
        session.add(user)
        await session.flush()
        session.add(
            Order(
                user_id=user.id,
                order_no="E2E-10001",
                status="PAID",
                shipping_status="NOT_SHIPPED",
                product_name="测试商品",
                amount=299,
            )
        )
        await session.commit()

    async def override_get_db():
        async with session_factory() as session:
            yield session

    async def classify_as_refund(
        self,
        title: str,
        content: str,
    ) -> ClassificationExecution:
        return ClassificationExecution(
            classification=TicketClassification(
                category="REFUND",
                priority="HIGH",
                intent="refund_or_return",
                route_to="after_sales",
            ),
            source="rule_based",
            fallback_used=True,
            attempts=1,
            latency_ms=1,
        )

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(
        "app.tools.order_tools.AsyncSessionLocal",
        session_factory,
    )
    monkeypatch.setattr(
        "app.tools.refund_tools.AsyncSessionLocal",
        session_factory,
    )
    monkeypatch.setattr(
        TicketClassificationService,
        "classify",
        classify_as_refund,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        yield client, session_factory

    app.dependency_overrides.clear()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def test_refund_confirmation_end_to_end(
    refund_client,
) -> None:
    client, session_factory = refund_client

    login_response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "refund-e2e@example.com",
            "password": "strong-password",
        },
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    create_response = await client.post(
        "/api/v1/tickets",
        headers=headers,
        json={
            "title": "申请退款",
            "content": "我要退订单E2E-10001",
        },
    )
    assert create_response.status_code == 201
    ticket_id = create_response.json()["id"]

    detail_response = await client.get(
        f"/api/v1/tickets/{ticket_id}",
        headers=headers,
    )
    messages = detail_response.json()["messages"]
    assert messages[-1]["sender_type"] == "AI"
    assert "299" in messages[-1]["content"]
    assert "是否确认" in messages[-1]["content"]

    runs_response = await client.get(
        f"/api/v1/tickets/{ticket_id}/agent-runs",
        headers=headers,
    )
    first_run = runs_response.json()[-1]
    assert first_run["checkpoint_status"] == (
        "waiting_for_confirmation"
    )
    assert first_run["state_snapshot"]["pending_action"][
        "tool_name"
    ] == "create_refund_request"

    confirm_response = await client.post(
        f"/api/v1/tickets/{ticket_id}/messages",
        headers=headers,
        json={"content": "确认"},
    )
    assert confirm_response.status_code == 200
    assert "退款申请" in confirm_response.json()["content"]
    assert "已创建" in confirm_response.json()["content"]

    async with session_factory() as session:
        refunds = list(
            (
                await session.execute(
                    select(RefundRequest)
                )
            ).scalars()
        )
        refund_count = await session.scalar(
            select(func.count()).select_from(
                RefundRequest
            )
        )

    assert refund_count == 1
    assert refunds[0].order_id is not None
    assert refunds[0].status == "PENDING"
    assert refunds[0].idempotency_key == (
        f"refund:{ticket_id}:E2E-10001"
    )

    final_runs_response = await client.get(
        f"/api/v1/tickets/{ticket_id}/agent-runs",
        headers=headers,
    )
    final_run = final_runs_response.json()[-1]
    assert final_run["checkpoint_status"] == "completed"
    assert final_run["classification_source"] == "checkpoint"
    assert final_run["state_snapshot"]["pending_action"] is None
    assert len(final_run["state_snapshot"]["tool_history"]) == 2
