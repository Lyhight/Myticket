from unittest.mock import AsyncMock

from app.agent.schemas import ClassificationExecution, TicketClassification
from app.agent.state import AgentState
from app.agent.tool_context import ToolExecutionContext
from app.agent.workflows.refund import RefundWorkflow


def classification() -> ClassificationExecution:
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


def context() -> ToolExecutionContext:
    return ToolExecutionContext(user_id=1, ticket_id=10)


async def test_refund_without_order_id_asks_user() -> None:
    executor = AsyncMock()
    workflow = RefundWorkflow(executor)
    state = AgentState(
        ticket_id=10,
        title="退款",
        user_message="我要退款",
        category="REFUND",
        priority="HIGH",
        intent="refund_or_return",
        route_to="after_sales",
    )

    result = await workflow.start(
        state=state,
        execution=classification(),
        context=context(),
    )

    assert result.state.current_step == "waiting_for_user"
    assert result.state.missing_fields == ["order_id"]
    executor.execute.assert_not_awaited()


async def test_eligible_refund_waits_for_confirmation() -> None:
    executor = AsyncMock()
    executor.execute.return_value = {
        "success": True,
        "eligible": True,
        "requires_human": False,
        "amount": 299,
        "reason": "PAID_ORDER_NOT_SHIPPED",
    }
    workflow = RefundWorkflow(executor)
    state = AgentState(
        ticket_id=10,
        title="退款",
        user_message="订单10001不想要了",
        category="REFUND",
        priority="HIGH",
        intent="refund_or_return",
        route_to="after_sales",
        entities={"order_id": "10001"},
    )

    result = await workflow.start(
        state=state,
        execution=classification(),
        context=context(),
    )

    assert result.state.current_step == "waiting_for_confirmation"
    assert result.state.pending_action is not None
    assert result.state.pending_action.tool_args["idempotency_key"] == (
        "refund:1:10001"
    )
    assert result.state.pending_action.confirmation_hash
    assert "299" in result.result.reply


async def test_confirmed_refund_executes_pending_tool() -> None:
    executor = AsyncMock()
    executor.execute.side_effect = [
        {
            "success": True,
            "eligible": True,
            "requires_human": False,
            "amount": 299,
        },
        {
            "success": True,
            "created": True,
            "refund": {
                "request_no": "RF-123",
                "status": "PENDING",
            },
        },
    ]
    workflow = RefundWorkflow(executor)
    state = AgentState(
        ticket_id=10,
        title="退款",
        user_message="退订单10001",
        category="REFUND",
        priority="HIGH",
        intent="refund_or_return",
        route_to="after_sales",
        entities={"order_id": "10001"},
    )
    waiting = await workflow.start(
        state=state,
        execution=classification(),
        context=context(),
    )

    completed = await workflow.resume(
        previous_state=waiting.state,
        content="确认",
        context=context(),
    )

    assert completed.state.current_step == "completed"
    assert completed.state.pending_action is None
    assert completed.result.action.tool_args["confirmed"] is True
    assert completed.result.reply == (
        "退款申请RF-123已创建，请等待处理。"
    )
    assert len(completed.state.tool_history) == 2


async def test_rejected_refund_does_not_execute_tool() -> None:
    executor = AsyncMock()
    executor.execute.return_value = {
        "success": True,
        "eligible": True,
        "requires_human": False,
        "amount": 299,
    }
    workflow = RefundWorkflow(executor)
    state = AgentState(
        ticket_id=10,
        title="退款",
        user_message="退订单10001",
        category="REFUND",
        priority="HIGH",
        intent="refund_or_return",
        route_to="after_sales",
        entities={"order_id": "10001"},
    )
    waiting = await workflow.start(
        state=state,
        execution=classification(),
        context=context(),
    )
    executor.execute.reset_mock()

    rejected = await workflow.resume(
        previous_state=waiting.state,
        content="取消",
        context=context(),
    )

    assert rejected.state.current_step == "completed"
    assert rejected.state.pending_action is None
    assert rejected.result.reply == "已取消本次退款操作。"
    executor.execute.assert_not_awaited()


async def test_unclear_confirmation_keeps_checkpoint() -> None:
    executor = AsyncMock()
    executor.execute.return_value = {
        "success": True,
        "eligible": True,
        "requires_human": False,
        "amount": 299,
    }
    workflow = RefundWorkflow(executor)
    state = AgentState(
        ticket_id=10,
        title="退款",
        user_message="退订单10001",
        category="REFUND",
        priority="HIGH",
        intent="refund_or_return",
        route_to="after_sales",
        entities={"order_id": "10001"},
    )
    waiting = await workflow.start(
        state=state,
        execution=classification(),
        context=context(),
    )
    executor.execute.reset_mock()

    unclear = await workflow.resume(
        previous_state=waiting.state,
        content="这个金额对吗",
        context=context(),
    )

    assert unclear.state.current_step == "waiting_for_confirmation"
    assert unclear.state.pending_action is not None
    executor.execute.assert_not_awaited()
