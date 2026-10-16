from collections.abc import Callable
import json

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.customer_service_agent import (
    CustomerServiceAgent,
)
from app.agent.schemas import (
    AgentAction,
    ClassificationExecution,
    CustomerServiceAgentResult,
    ReviewResult,
    TicketClassification,
)
from app.agent.state import AgentExecution, AgentState
from app.models.agent_task import AgentTask
from app.models.user_memory import UserMemory


def make_agent_result(
    *,
    priority: str = "NORMAL",
    reply: str = "您好，您的订单当前状态为已付款。",
    review_approved: bool = True,
) -> CustomerServiceAgentResult:
    return CustomerServiceAgentResult(
        classification_execution=ClassificationExecution(
            classification=TicketClassification(
                category="ORDER",
                priority=priority,
                intent="order_query",
                route_to="order_support",
            ),
            source="qwen",
            fallback_used=False,
            attempts=1,
            latency_ms=10,
        ),
        action=AgentAction(
            action="direct_reply",
            reason="Test decision",
        ),
        tool_result=None,
        reply=reply,
        review=ReviewResult(
            approved=review_approved,
            issues=(
                []
                if review_approved
                else ["Test review rejection"]
            ),
        ),
    )


@pytest.fixture
def mock_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[..., None]:
    def install(
        result: CustomerServiceAgentResult,
    ) -> None:
        async def fake_run_with_state(
            self,
            title: str,
            content: str,
            history=None,
            user_id=None,
            ticket_id=None,
            previous_state=None,
            long_term_memories=None,
            retrieved_knowledge=None,
        ) -> AgentExecution:
            classification = (
                result.classification_execution.classification
            )
            waiting_human = (
                classification.priority == "URGENT"
                or (
                    result.review is not None
                    and not result.review.approved
                )
            )
            state = AgentState(
                ticket_id=ticket_id,
                title=title,
                user_message=content,
                category=classification.category,
                priority=classification.priority,
                intent=classification.intent,
                route_to=classification.route_to,
                action=result.action,
                reply=result.reply,
                review=result.review,
                current_step=(
                    "waiting_for_human"
                    if waiting_human
                    else "completed"
                ),
            )
            return AgentExecution(
                state=state,
                result=result,
            )

        monkeypatch.setattr(
            CustomerServiceAgent,
            "run_with_state",
            fake_run_with_state,
        )

    return install


async def register_and_login(
    client: AsyncClient,
    *,
    email: str,
    password: str = "strong-password",
) -> str:
    register_response = await client.post(
        "/api/v1/users",
        json={
            "email": email,
            "password": password,
        },
    )
    assert register_response.status_code == 201

    login_response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": password,
        },
    )
    assert login_response.status_code == 200
    return login_response.json()["access_token"]


def auth_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
    }


async def create_ticket(
    client: AsyncClient,
    token: str,
    request_id: str | None = None,
):
    headers = auth_headers(token)
    if request_id:
        headers["X-Request-ID"] = request_id
    return await client.post(
        "/api/v1/tickets",
        headers=headers,
        json={
            "title": "查询订单",
            "content": "请查询订单10001",
        },
    )


async def test_create_list_and_get_ticket(
    client: AsyncClient,
    mock_agent,
) -> None:
    mock_agent(make_agent_result())
    token = await register_and_login(
        client,
        email="owner@example.com",
    )

    create_response = await create_ticket(
        client,
        token,
        request_id="ticket-create-request-123",
    )

    assert create_response.status_code == 201
    ticket = create_response.json()
    assert ticket["category"] == "ORDER"
    assert ticket["priority"] == "NORMAL"
    assert ticket["status"] == "OPEN"
    assert ticket["classification_source"] == "qwen"

    list_response = await client.get(
        "/api/v1/tickets",
        headers=auth_headers(token),
    )
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    detail_response = await client.get(
        f"/api/v1/tickets/{ticket['id']}",
        headers=auth_headers(token),
    )
    assert detail_response.status_code == 200

    messages = detail_response.json()["messages"]
    assert [item["sender_type"] for item in messages] == [
        "CUSTOMER",
        "AI",
    ]
    assert messages[0]["content"] == "请查询订单10001"

    runs_response = await client.get(
        f"/api/v1/tickets/{ticket['id']}/agent-runs",
        headers=auth_headers(token),
    )
    assert runs_response.status_code == 200
    runs = runs_response.json()
    assert len(runs) == 1
    assert runs[0]["checkpoint_status"] == "completed"
    assert runs[0]["state_snapshot"]["ticket_id"] == ticket["id"]
    assert runs[0]["rag_trace"]["result_count"] == 0
    assert runs[0]["memory_trace"]["long_term_memory_count"] == 0
    assert runs[0]["context_trace"] == {}
    assert runs[0]["total_latency_ms"] >= 0
    assert runs[0]["correlation_id"] == "ticket-create-request-123"


async def test_ticket_input_limits_are_enforced(
    client: AsyncClient,
) -> None:
    token = await register_and_login(
        client,
        email="validation@example.com",
    )

    response = await client.post(
        "/api/v1/tickets",
        headers=auth_headers(token),
        json={"title": "   ", "content": "normal"},
    )

    assert response.status_code == 422


async def test_public_task_status_hides_worker_internals(
    client: AsyncClient,
    mock_agent,
) -> None:
    mock_agent(make_agent_result())
    token = await register_and_login(
        client,
        email="async-task@example.com",
    )
    ticket_id = (await create_ticket(client, token)).json()["id"]

    accepted = await client.post(
        f"/api/v1/tickets/{ticket_id}/messages/async",
        headers={
            **auth_headers(token),
            "Idempotency-Key": "public-task-key",
        },
        json={"content": "异步查询订单"},
    )
    assert accepted.status_code == 202
    accepted_body = accepted.json()
    assert accepted_body["idempotency_key"] == "public-task-key"

    status_response = await client.get(
        f"/api/v1/tickets/{ticket_id}/tasks/{accepted_body['task_id']}",
        headers=auth_headers(token),
    )
    body = status_response.json()
    assert status_response.status_code == 200
    assert "payload" not in body
    assert "last_error" not in body
    assert "locked_by" not in body


async def test_user_cannot_read_another_users_ticket(
    client: AsyncClient,
    mock_agent,
) -> None:
    mock_agent(make_agent_result())

    owner_token = await register_and_login(
        client,
        email="owner@example.com",
    )
    create_response = await create_ticket(
        client,
        owner_token,
    )
    ticket_id = create_response.json()["id"]

    other_token = await register_and_login(
        client,
        email="other@example.com",
    )
    response = await client.get(
        f"/api/v1/tickets/{ticket_id}",
        headers=auth_headers(other_token),
    )

    assert response.status_code == 403


async def test_owner_can_delete_ticket_but_other_user_cannot(
    client: AsyncClient,
    mock_agent,
    db_session: AsyncSession,
) -> None:
    mock_agent(make_agent_result())
    owner_token = await register_and_login(
        client,
        email="delete-owner@example.com",
    )
    other_token = await register_and_login(
        client,
        email="delete-other@example.com",
    )
    create_response = await create_ticket(client, owner_token)
    ticket_id = create_response.json()["id"]
    owner_user_id = create_response.json()["user_id"]
    db_session.add(UserMemory(
        user_id=owner_user_id,
        memory_type="explicit",
        content="用户明确要求记住：使用中文",
        fingerprint="delete-ticket-memory",
        memory_key="response_language",
        source_ticket_id=ticket_id,
    ))
    await db_session.commit()
    message_response = await client.post(
        f"/api/v1/tickets/{ticket_id}/messages",
        headers={
            **auth_headers(owner_token),
            "Idempotency-Key": "delete-task-0001",
        },
        json={"content": "删除前再问一次"},
    )
    assert message_response.status_code == 200

    forbidden_response = await client.delete(
        f"/api/v1/tickets/{ticket_id}",
        headers=auth_headers(other_token),
    )
    assert forbidden_response.status_code == 403

    delete_response = await client.delete(
        f"/api/v1/tickets/{ticket_id}",
        headers=auth_headers(owner_token),
    )
    assert delete_response.status_code == 204

    detail_response = await client.get(
        f"/api/v1/tickets/{ticket_id}",
        headers=auth_headers(owner_token),
    )
    assert detail_response.status_code == 404
    remaining_tasks = list(
        (
            await db_session.execute(
                select(AgentTask).where(AgentTask.ticket_id == ticket_id)
            )
        ).scalars()
    )
    assert remaining_tasks == []
    remaining_memories = list(
        (
            await db_session.execute(
                select(UserMemory).where(
                    UserMemory.source_ticket_id == ticket_id
                )
            )
        ).scalars()
    )
    assert remaining_memories == []


async def test_message_stream_reports_stages_and_reply(
    client: AsyncClient,
    mock_agent,
) -> None:
    mock_agent(make_agent_result(reply="这是流式测试回复。"))
    token = await register_and_login(
        client,
        email="stream-owner@example.com",
    )
    create_response = await create_ticket(client, token)
    ticket_id = create_response.json()["id"]

    response = await client.post(
        f"/api/v1/tickets/{ticket_id}/messages/stream",
        headers=auth_headers(token),
        json={"content": "请继续查询"},
    )
    assert response.status_code == 200
    events = [
        json.loads(line)
        for line in response.text.splitlines()
        if line.strip()
    ]
    assert [event["type"] for event in events[:3]] == [
        "status", "status", "status",
    ]
    assert "".join(
        event["content"]
        for event in events
        if event["type"] == "delta"
    ) == "这是流式测试回复。"
    assert events[-1]["type"] == "done"


async def test_urgent_ticket_enters_review_and_admin_approves(
    client: AsyncClient,
    mock_agent,
    admin_user,
) -> None:
    mock_agent(
        make_agent_result(
            priority="URGENT",
            reply="这是等待人工确认的回复草稿。",
        )
    )

    owner_token = await register_and_login(
        client,
        email="owner@example.com",
    )
    create_response = await create_ticket(
        client,
        owner_token,
    )

    assert create_response.status_code == 201
    ticket = create_response.json()
    assert ticket["status"] == "PENDING_REVIEW"

    blocked_message = await client.post(
        f"/api/v1/tickets/{ticket['id']}/messages",
        headers=auth_headers(owner_token),
        json={"content": "审批前继续发送"},
    )
    assert blocked_message.status_code == 409

    admin_login = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "admin@example.com",
            "password": "admin-password",
        },
    )
    assert admin_login.status_code == 200
    admin_token = admin_login.json()["access_token"]

    pending_response = await client.get(
        "/api/v1/tickets/pending",
        headers=auth_headers(admin_token),
    )
    assert pending_response.status_code == 200
    assert len(pending_response.json()) == 1

    approve_response = await client.post(
        f"/api/v1/tickets/{ticket['id']}/approve",
        headers=auth_headers(admin_token),
    )
    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "RESOLVED"

    mock_agent(make_agent_result())
    reopened_message = await client.post(
        f"/api/v1/tickets/{ticket['id']}/messages",
        headers=auth_headers(owner_token),
        json={"content": "解决后还有一个问题"},
    )
    assert reopened_message.status_code == 200

    detail_response = await client.get(
        f"/api/v1/tickets/{ticket['id']}",
        headers=auth_headers(owner_token),
    )
    messages = detail_response.json()["messages"]
    assert detail_response.json()["status"] == "OPEN"
    assert [item["sender_type"] for item in messages] == [
        "CUSTOMER", "AI", "CUSTOMER", "AI",
    ]
    assert messages[1]["content"] == "这是等待人工确认的回复草稿。"
