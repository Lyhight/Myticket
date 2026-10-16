from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock

import pytest

from app.agent.confirmation import ConfirmationDetector
from app.agent.customer_service_agent import CustomerServiceAgent
from app.agent.schemas import (
    AgentAction,
    ClassificationExecution,
    TicketClassification,
)
from app.agent.state import AgentState, PendingAction


@pytest.mark.parametrize(
    "content",
    [
        "确认",
        "确定",
        "同意",
        "是的",
        "确认退款",
        "好的，确认",
    ],
)
def test_explicit_confirmation_is_detected(
    content: str,
) -> None:
    assert ConfirmationDetector().detect(content) == "confirm"


@pytest.mark.parametrize(
    "content",
    [
        "取消",
        "不确认",
        "不同意",
        "算了",
        "先不要",
        "不退款",
    ],
)
def test_explicit_rejection_is_detected(
    content: str,
) -> None:
    assert ConfirmationDetector().detect(content) == "reject"


@pytest.mark.parametrize(
    "content",
    [
        "",
        "我再考虑一下",
        "这个金额对吗",
        "确认之后多久能到账",
        "好的",
    ],
)
def test_ambiguous_message_is_not_confirmation(
    content: str,
) -> None:
    assert ConfirmationDetector().detect(content) == "unknown"


def test_pending_action_expiration() -> None:
    now = datetime.now(timezone.utc)
    active = PendingAction(
        tool_name="create_refund_request",
        expires_at=now + timedelta(minutes=10),
    )
    expired = PendingAction(
        tool_name="create_refund_request",
        expires_at=now - timedelta(seconds=1),
    )

    assert active.is_expired(now) is False
    assert expired.is_expired(now) is True


async def test_agent_can_pause_for_confirmation() -> None:
    agent = CustomerServiceAgent()
    agent.classifier = Mock()
    agent.classifier.classify = AsyncMock(
        return_value=ClassificationExecution(
            classification=TicketClassification(
                category="ORDER",
                priority="NORMAL",
                intent="cancel_order",
                route_to="order_support",
            ),
            source="qwen",
            fallback_used=False,
            attempts=1,
            latency_ms=10,
        )
    )
    agent._decide_or_fallback = AsyncMock(
        return_value=AgentAction(
            action="request_confirmation",
            tool_name="cancel_order",
            tool_args={
                "order_id": "10001",
                "reason": "不再需要",
            },
            reason="Cancellation requires confirmation",
            message="确认取消订单10001吗？",
        )
    )
    agent.tool_executor = Mock()
    agent.tool_executor.execute = AsyncMock()

    execution = await agent.run_with_state(
        ticket_id=10,
        user_id=20,
        title="取消订单",
        content="我要取消订单10001",
    )

    state = execution.state
    assert state.current_step == "waiting_for_confirmation"
    assert state.requires_confirmation is True
    assert state.confirmation_summary == "确认取消订单10001吗？"
    assert state.pending_action is not None
    assert state.pending_action.tool_name == (
        "cancel_order"
    )
    assert state.pending_action.tool_args["order_id"] == "10001"
    agent.tool_executor.execute.assert_not_awaited()


def test_pending_action_survives_checkpoint_roundtrip() -> None:
    state = AgentState(
        ticket_id=10,
        title="退款申请",
        user_message="我要退款",
        current_step="waiting_for_confirmation",
        requires_confirmation=True,
        confirmation_summary="确认退款吗？",
        pending_action=PendingAction(
            tool_name="create_refund_request",
            tool_args={"order_id": "10001"},
            expires_at=(
                datetime.now(timezone.utc)
                + timedelta(minutes=10)
            ),
        ),
    )

    restored = AgentState.model_validate(
        state.model_dump(mode="json")
    )

    assert restored == state
