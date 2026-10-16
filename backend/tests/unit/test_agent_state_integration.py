from unittest.mock import ANY, AsyncMock, Mock

from app.agent.customer_service_agent import (
    SAFE_REPLY_AFTER_REJECT,
    CustomerServiceAgent,
)
from app.agent.schemas import (
    AgentAction,
    ClassificationExecution,
    ReviewResult,
    TicketClassification,
)
from app.agent.tool_context import ToolExecutionContext
from app.agent.state import AgentState


def make_agent() -> CustomerServiceAgent:
    agent = CustomerServiceAgent()

    agent.classifier = Mock()
    agent.classifier.classify = AsyncMock(
        return_value=ClassificationExecution(
            classification=TicketClassification(
                category="ORDER",
                priority="NORMAL",
                intent="order_query",
                route_to="order_support",
            ),
            source="qwen",
            fallback_used=False,
            attempts=1,
            latency_ms=10,
        )
    )
    agent._decide_or_fallback = AsyncMock()
    agent.tool_executor = Mock()
    agent.tool_executor.execute = AsyncMock()
    agent.reply_service = Mock()
    agent.reply_service.generate = AsyncMock()
    agent.review_service = Mock()
    agent.review_service.review = AsyncMock(
        return_value=ReviewResult(approved=True, issues=[]),
    )
    return agent


async def test_ask_user_state_waits_for_user() -> None:
    agent = make_agent()
    agent._decide_or_fallback.return_value = AgentAction(
        action="ask_user",
        reason="Order ID is missing",
        message="请提供订单号。",
    )

    execution = await agent.run_with_state(
        ticket_id=10,
        title="查询订单",
        content="帮我查询",
        history=[
            {
                "role": "assistant",
                "content": "请问需要什么帮助？",
            },
        ],
    )

    assert execution.result.reply == "请提供订单号。"
    assert execution.state.ticket_id == 10
    assert execution.state.category == "ORDER"
    assert execution.state.current_step == "waiting_for_user"
    assert execution.state.action is not None
    assert execution.state.action.action == "ask_user"
    assert execution.state.history[0].role == "assistant"


async def test_tool_execution_is_recorded_in_state() -> None:
    agent = make_agent()
    action = AgentAction(
        action="tool",
        tool_name="get_order",
        tool_args={"order_id": "10001"},
        reason="Query order",
    )
    tool_result = {
        "success": True,
        "order": {
            "order_id": "10001",
            "status": "PAID",
        },
    }

    agent._decide_or_fallback.return_value = action
    agent.tool_executor.execute.return_value = tool_result
    agent.reply_service.generate.return_value = (
        "订单10001当前状态为已付款。"
    )
    agent.review_service.review.return_value = ReviewResult(
        approved=True,
        issues=[],
    )

    execution = await agent.run_with_state(
        title="查询订单",
        content="查询订单10001",
    )

    state = execution.state
    assert state.current_step == "completed"
    assert state.reply == "订单10001当前状态为已付款。"
    assert state.review is not None
    assert state.review.approved is True
    assert len(state.tool_history) == 1
    assert state.tool_history[0].tool_name == "get_order"
    assert state.tool_history[0].success is True
    assert state.tool_history[0].result == tool_result


async def test_rejected_reply_state_waits_for_human() -> None:
    agent = make_agent()
    agent._decide_or_fallback.return_value = AgentAction(
        action="direct_reply",
        reason="No tool required",
    )
    agent.tool_executor.execute.return_value = None
    agent.reply_service.generate.return_value = (
        "内部 tool_result 显示处理成功。"
    )
    agent.review_service.review.return_value = ReviewResult(
        approved=False,
        issues=["回复泄露内部字段"],
    )

    execution = await agent.run_with_state(
        title="订单问题",
        content="帮我处理订单",
    )

    assert execution.result.reply == SAFE_REPLY_AFTER_REJECT
    assert execution.state.reply == SAFE_REPLY_AFTER_REJECT
    assert execution.state.current_step == "waiting_for_human"
    assert execution.state.review is not None
    assert execution.state.review.approved is False


async def test_original_run_api_remains_compatible() -> None:
    agent = make_agent()
    agent._decide_or_fallback.return_value = AgentAction(
        action="ask_user",
        reason="Missing information",
        message="请补充订单号。",
    )

    result = await agent.run(
        title="查询订单",
        content="查询一下",
    )

    assert result.reply == "请补充订单号。"
    assert result.action.action == "ask_user"


async def test_missing_tool_argument_is_blocked() -> None:
    agent = make_agent()
    agent._decide_or_fallback.return_value = AgentAction(
        action="tool",
        tool_name="get_order",
        tool_args={},
        reason="Query order",
    )

    execution = await agent.run_with_state(
        title="查询订单",
        content="帮我查询一下",
    )

    assert execution.result.action.action == "ask_user"
    assert execution.result.reply == "请提供需要查询的订单号。"
    assert execution.state.missing_fields == ["order_id"]
    assert execution.state.current_step == "waiting_for_user"
    agent.tool_executor.execute.assert_not_awaited()


async def test_extracted_entity_completes_tool_arguments() -> None:
    agent = make_agent()
    action = AgentAction(
        action="tool",
        tool_name="get_order",
        tool_args={},
        reason="Query order",
    )
    agent._decide_or_fallback.return_value = action
    agent.tool_executor.execute.return_value = {
        "success": True,
        "order": {"order_id": "10001"},
    }
    agent.reply_service.generate.return_value = "订单查询成功。"
    agent.review_service.review.return_value = ReviewResult(
        approved=True,
        issues=[],
    )

    execution = await agent.run_with_state(
        title="查询订单",
        content="请查询订单号10001",
        user_id=42,
        ticket_id=7,
    )

    assert action.tool_args == {"order_id": "10001"}
    assert execution.state.entities["order_id"] == "10001"
    assert execution.state.missing_fields == []
    assert execution.state.current_step == "completed"
    agent.tool_executor.execute.assert_awaited_once_with(
        action,
        context=ToolExecutionContext(
            user_id=42,
            ticket_id=7,
        ),
        state=ANY,
    )


async def test_normal_run_restores_previous_working_memory() -> None:
    agent = make_agent()
    agent._decide_or_fallback.return_value = AgentAction(
        action="ask_user",
        reason="Need more information",
        message="请继续补充信息。",
    )
    previous_state = AgentState(
        ticket_id=7,
        title="查询订单",
        user_message="查询订单10001",
        conversation_summary="用户正在查询订单。",
        entities={"order_id": "10001"},
        missing_fields=["tracking_number"],
        current_step="waiting_for_user",
    )

    execution = await agent.run_with_state(
        title="查询订单",
        content="继续",
        ticket_id=7,
        previous_state=previous_state,
    )

    assert execution.state.conversation_summary == (
        "用户正在查询订单。"
    )
    assert execution.state.entities["order_id"] == "10001"
    assert execution.state.missing_fields == ["tracking_number"]
