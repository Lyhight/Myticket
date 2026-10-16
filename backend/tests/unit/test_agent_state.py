from app.agent.schemas import AgentAction
from app.agent.state import (
    AgentState,
    ConversationTurn,
)


def test_state_has_safe_independent_defaults() -> None:
    first = AgentState(
        title="第一张工单",
        user_message="查询订单10001",
    )
    second = AgentState(
        title="第二张工单",
        user_message="查询订单10002",
    )

    first.entities["order_id"] = "10001"
    first.missing_fields.append("tracking_number")

    assert second.entities == {}
    assert second.missing_fields == []
    assert first.current_step == "received"


def test_state_can_store_conversation_and_decision() -> None:
    state = AgentState(
        ticket_id=10,
        title="查询订单",
        user_message="订单现在到哪里了",
        history=[
            ConversationTurn(
                role="assistant",
                content="请提供订单号。",
            ),
        ],
        missing_fields=["order_id"],
        current_step="waiting_for_user",
    )

    state.entities["order_id"] = "10001"
    state.missing_fields.clear()
    state.action = AgentAction(
        action="tool",
        tool_name="get_order",
        tool_args={"order_id": "10001"},
        reason="Order ID is available",
    )
    state.current_step = "executing_tool"

    assert state.history[0].role == "assistant"
    assert state.entities["order_id"] == "10001"
    assert state.missing_fields == []
    assert state.action.tool_name == "get_order"


def test_record_successful_tool_execution() -> None:
    state = AgentState(
        title="查询订单",
        user_message="查询订单10001",
    )

    state.record_tool_execution(
        tool_name="get_order",
        arguments={"order_id": "10001"},
        result={
            "success": True,
            "order": {"order_id": "10001"},
        },
    )

    record = state.tool_history[0]
    assert record.tool_name == "get_order"
    assert record.arguments == {"order_id": "10001"}
    assert record.success is True


def test_record_failed_tool_execution() -> None:
    state = AgentState(
        title="查询订单",
        user_message="查询订单99999",
    )

    state.record_tool_execution(
        tool_name="get_order",
        arguments={"order_id": "99999"},
        result={
            "success": False,
            "error": "ORDER_NOT_FOUND",
        },
    )

    assert state.tool_history[0].success is False


def test_add_error_marks_state_as_failed() -> None:
    state = AgentState(
        title="测试错误",
        user_message="执行任务",
        current_step="executing_tool",
    )

    state.add_error("Tool execution failed")

    assert state.current_step == "failed"
    assert state.errors == ["Tool execution failed"]


def test_confirmation_is_idempotent() -> None:
    state = AgentState(
        title="取消订单",
        user_message="确认取消",
        requires_confirmation=True,
    )

    state.confirm_action("cancel_order")
    state.confirm_action("cancel_order")

    assert state.requires_confirmation is False
    assert state.confirmed_actions == ["cancel_order"]


def test_state_can_be_serialized_for_checkpoint() -> None:
    state = AgentState(
        ticket_id=20,
        title="退款申请",
        user_message="我要退款",
        entities={"order_id": "10001"},
        current_step="waiting_for_confirmation",
        requires_confirmation=True,
    )

    payload = state.model_dump(mode="json")
    restored = AgentState.model_validate(payload)

    assert restored == state
