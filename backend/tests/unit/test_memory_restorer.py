from app.agent.memory.restorer import ShortTermMemoryRestorer
from app.agent.state import AgentState


def test_restorer_carries_reusable_working_memory() -> None:
    previous = AgentState(
        ticket_id=7,
        title="订单咨询",
        user_message="查询订单10001",
        conversation_summary="用户正在查询订单。",
        context_metadata={"summarized_message_count": 4},
        entities={"order_id": "10001"},
        missing_fields=["tracking_number"],
    )
    previous.record_tool_execution(
        tool_name="get_order",
        arguments={"order_id": "10001"},
        result={"success": True},
    )
    current = AgentState(
        ticket_id=7,
        title="订单咨询",
        user_message="继续",
    )

    restored = ShortTermMemoryRestorer().restore(
        state=current,
        previous_state=previous,
    )

    assert restored.conversation_summary == "用户正在查询订单。"
    assert restored.entities == {"order_id": "10001"}
    assert restored.missing_fields == ["tracking_number"]
    assert restored.context_metadata["summarized_message_count"] == 4
    assert restored.tool_history[0].tool_name == "get_order"


def test_restorer_does_not_mix_different_tickets() -> None:
    previous = AgentState(
        ticket_id=8,
        title="其他工单",
        user_message="订单10002",
        entities={"order_id": "10002"},
    )
    current = AgentState(
        ticket_id=7,
        title="当前工单",
        user_message="继续",
    )

    restored = ShortTermMemoryRestorer().restore(
        state=current,
        previous_state=previous,
    )

    assert restored.entities == {}


def test_restorer_limits_historical_tool_results() -> None:
    previous = AgentState(
        ticket_id=7,
        title="订单咨询",
        user_message="继续",
    )
    for index in range(5):
        previous.record_tool_execution(
            tool_name="get_order",
            arguments={"order_id": str(index)},
            result={"success": True, "index": index},
        )

    restored = ShortTermMemoryRestorer(
        max_tool_results=2
    ).restore(
        state=AgentState(
            ticket_id=7,
            title="订单咨询",
            user_message="继续",
        ),
        previous_state=previous,
    )

    assert len(restored.tool_history) == 2
    assert restored.tool_history[0].result["index"] == 3
    assert restored.tool_history[1].result["index"] == 4
