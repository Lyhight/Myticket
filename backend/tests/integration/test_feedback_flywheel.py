from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feedback import KnowledgeGap
from app.models.message import Message
from app.models.ticket import Ticket
from app.models.user import User


async def _login(client: AsyncClient, email: str, password: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _conversation(db: AsyncSession, user_id: int):
    ticket = Ticket(user_id=user_id, title="积分问题")
    db.add(ticket)
    await db.flush()
    question = Message(
        ticket_id=ticket.id,
        sender_type="CUSTOMER",
        content="退款以后会员积分什么时候退回？",
    )
    answer = Message(
        ticket_id=ticket.id,
        sender_type="AI",
        content="暂时无法确认积分返还时间。",
    )
    db.add_all([question, answer])
    await db.commit()
    await db.refresh(ticket)
    await db.refresh(answer)
    return ticket, answer


async def test_negative_feedback_becomes_reviewed_knowledge(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_user,
) -> None:
    created = await client.post(
        "/api/v1/users",
        json={"email": "feedback@example.com", "password": "strong-password"},
    )
    assert created.status_code == 201
    customer = (
        await db_session.execute(
            select(User).where(User.email == "feedback@example.com")
        )
    ).scalar_one()
    ticket, answer = await _conversation(db_session, customer.id)
    customer_token = await _login(
        client, "feedback@example.com", "strong-password"
    )

    feedback = await client.post(
        "/api/v1/feedback",
        headers=_headers(customer_token),
        json={
            "ticket_id": ticket.id,
            "message_id": answer.id,
            "rating": "DOWN",
            "comment": "没有解决问题",
        },
    )
    assert feedback.status_code == 201
    assert feedback.json()["rating"] == "DOWN"

    persisted = await client.get(
        f"/api/v1/feedback?ticket_id={ticket.id}",
        headers=_headers(customer_token),
    )
    assert persisted.status_code == 200
    assert persisted.json()[0]["message_id"] == answer.id
    assert persisted.json()[0]["rating"] == "DOWN"

    admin_token = await _login(client, "admin@example.com", "admin-password")
    gaps = await client.get(
        "/api/v1/feedback/gaps?status=PENDING",
        headers=_headers(admin_token),
    )
    assert gaps.status_code == 200
    assert len(gaps.json()) == 1
    gap = gaps.json()[0]
    assert gap["question"] == "退款以后会员积分什么时候退回？"
    assert gap["reason"] == "negative_feedback"

    approved = await client.post(
        f"/api/v1/feedback/gaps/{gap['id']}/approve",
        headers=_headers(admin_token),
        json={
            "approved_answer": "退款完成后，积分将在一至三个工作日内原路扣回。",
            "reviewer_note": "已核对积分政策",
        },
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "APPROVED"
    assert approved.json()["knowledge_document_id"] is not None

    search = await client.post(
        "/api/v1/knowledge/search",
        headers=_headers(admin_token),
        json={"query": "退款积分什么时候退回", "top_k": 3},
    )
    assert search.status_code == 200
    assert search.json()[0]["source"].startswith("flywheel://knowledge-gap/")


async def test_feedback_requires_ticket_ownership_and_agent_message(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    for email in ("owner@example.com", "other@example.com"):
        response = await client.post(
            "/api/v1/users",
            json={"email": email, "password": "strong-password"},
        )
        assert response.status_code == 201
    users = {
        user.email: user
        for user in (
            await db_session.execute(
                select(User).where(
                    User.email.in_(["owner@example.com", "other@example.com"])
                )
            )
        ).scalars()
    }
    ticket, answer = await _conversation(db_session, users["owner@example.com"].id)
    other_token = await _login(client, "other@example.com", "strong-password")

    response = await client.post(
        "/api/v1/feedback",
        headers=_headers(other_token),
        json={
            "ticket_id": ticket.id,
            "message_id": answer.id,
            "rating": "DOWN",
        },
    )
    assert response.status_code == 403


async def test_duplicate_negative_feedback_is_idempotent(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await client.post(
        "/api/v1/users",
        json={"email": "repeat@example.com", "password": "strong-password"},
    )
    customer = (
        await db_session.execute(
            select(User).where(User.email == "repeat@example.com")
        )
    ).scalar_one()
    ticket, answer = await _conversation(db_session, customer.id)
    token = await _login(client, "repeat@example.com", "strong-password")
    body = {
        "ticket_id": ticket.id,
        "message_id": answer.id,
        "rating": "DOWN",
    }
    first = await client.post("/api/v1/feedback", headers=_headers(token), json=body)
    second = await client.post("/api/v1/feedback", headers=_headers(token), json=body)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    gap = (await db_session.execute(select(KnowledgeGap))).scalar_one()
    assert gap.occurrence_count == 1

    another_ticket, another_answer = await _conversation(db_session, customer.id)
    recurrence = await client.post(
        "/api/v1/feedback",
        headers=_headers(token),
        json={
            "ticket_id": another_ticket.id,
            "message_id": another_answer.id,
            "rating": "DOWN",
        },
    )
    assert recurrence.status_code == 201
    await db_session.refresh(gap)
    assert gap.occurrence_count == 2
