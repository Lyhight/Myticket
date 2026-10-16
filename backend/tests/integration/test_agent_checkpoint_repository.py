from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.schemas import (
    AgentAction,
    ClassificationExecution,
    CustomerServiceAgentResult,
    TicketClassification,
)
from app.agent.state import AgentState
from app.models.agent_run import AgentRun
from app.models.message import Message
from app.models.ticket import Ticket
from app.models.user import User
from app.repositories.agent_run_repository import (
    AgentRunRepository,
)
from app.core.logging import reset_correlation_id, set_correlation_id
from prometheus_client import generate_latest


def make_result() -> CustomerServiceAgentResult:
    return CustomerServiceAgentResult(
        classification_execution=ClassificationExecution(
            classification=TicketClassification(
                category="REFUND",
                priority="HIGH",
                intent="refund_or_return",
                route_to="after_sales",
            ),
            source="qwen",
            fallback_used=False,
            attempts=1,
            latency_ms=12,
        ),
        action=AgentAction(
            action="ask_user",
            reason="Waiting for confirmation",
            message="是否确认退款？",
        ),
        reply="是否确认退款？",
    )


async def create_ticket(
    db_session: AsyncSession,
) -> Ticket:
    user = User(
        email="checkpoint@example.com",
        password_hash="not-used",
    )
    db_session.add(user)
    await db_session.flush()

    ticket = Ticket(
        user_id=user.id,
        title="退款申请",
    )
    db_session.add(ticket)
    await db_session.flush()

    db_session.add(
        Message(
            ticket_id=ticket.id,
            sender_type="CUSTOMER",
            content="我要退款",
        )
    )
    await db_session.commit()
    await db_session.refresh(ticket)
    return ticket


async def test_state_snapshot_is_persisted_and_restored(
    db_session: AsyncSession,
) -> None:
    ticket = await create_ticket(db_session)
    state = AgentState(
        ticket_id=ticket.id,
        title="退款申请",
        user_message="我要退款",
        category="REFUND",
        priority="HIGH",
        intent="refund_or_return",
        route_to="after_sales",
        entities={"order_id": "10001"},
        current_step="waiting_for_confirmation",
        requires_confirmation=True,
    )
    repository = AgentRunRepository(db_session)

    run = await repository.create(
        ticket_id=ticket.id,
        result=make_result(),
        state=state,
        rag_trace={"result_count": 1},
        memory_trace={"long_term_memory_count": 2},
        context_trace={"estimated_tokens": 120},
        total_latency_ms=45.5,
    )

    assert run.checkpoint_status == (
        "waiting_for_confirmation"
    )
    assert run.state_snapshot is not None
    assert run.state_snapshot["entities"] == {
        "order_id": "10001"
    }
    assert run.rag_trace == {"result_count": 1}
    assert run.memory_trace == {"long_term_memory_count": 2}
    assert run.context_trace == {"estimated_tokens": 120}
    assert run.total_latency_ms == 45.5

    restored = await repository.get_latest_state_by_ticket(
        ticket.id
    )

    assert restored == state


async def test_legacy_run_without_state_remains_supported(
    db_session: AsyncSession,
) -> None:
    ticket = await create_ticket(db_session)
    repository = AgentRunRepository(db_session)

    run = await repository.create(
        ticket_id=ticket.id,
        result=make_result(),
    )

    assert run.state_snapshot is None
    assert run.checkpoint_status is None
    assert (
        await repository.get_latest_state_by_ticket(
            ticket.id
        )
        is None
    )


async def test_agent_run_persists_correlation_id(
    db_session: AsyncSession,
) -> None:
    ticket = await create_ticket(db_session)
    token = set_correlation_id("request-correlation-123")
    try:
        run = await AgentRunRepository(db_session).create(
            ticket_id=ticket.id,
            result=make_result(),
        )
    finally:
        reset_correlation_id(token)

    assert run.correlation_id == "request-correlation-123"


async def test_committed_agent_run_emits_bounded_business_metrics(
    db_session: AsyncSession,
) -> None:
    ticket = await create_ticket(db_session)

    await AgentRunRepository(db_session).create(
        ticket_id=ticket.id,
        result=make_result(),
        rag_trace={
            "retrieval_method": "keyword_fallback",
            "fallback_used": True,
            "result_count": 1,
            "latency_ms": 25.0,
        },
        total_latency_ms=80.0,
    )

    tool_result = make_result()
    tool_result.action = AgentAction(
        action="tool",
        tool_name="tenant_supplied_dynamic_tool",
        reason="Exercise cardinality protection",
    )
    tool_result.tool_result = {"success": False}
    await AgentRunRepository(db_session).create(
        ticket_id=ticket.id,
        result=tool_result,
        rag_trace={
            "retrieval_method": "tenant_supplied_dynamic_method",
            "fallback_used": False,
            "result_count": 0,
            "latency_ms": 1.0,
        },
    )

    metrics = generate_latest().decode("utf-8")
    assert (
        'myticket_agent_runs_total{action="ask_user",category="REFUND",'
        'outcome="completed",source="qwen"}'
    ) in metrics
    assert (
        'myticket_rag_retrievals_total{method="keyword_fallback",'
        'outcome="fallback"}'
    ) in metrics
    assert (
        'myticket_agent_run_duration_seconds_count{action="ask_user",'
        'category="REFUND"}'
    ) in metrics
    assert (
        'myticket_tool_executions_total{outcome="failure",tool="other"}'
    ) in metrics
    assert (
        'myticket_rag_retrievals_total{method="other",outcome="empty"}'
    ) in metrics
