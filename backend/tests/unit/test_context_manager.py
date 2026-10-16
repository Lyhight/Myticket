from app.agent.context.manager import ContextManager
from app.agent.schemas import AgentAction
from app.agent.state import (
    AgentState,
    ConversationTurn,
)


def test_context_selects_most_recent_messages() -> None:
    state = AgentState(
        title="查询订单",
        user_message="继续查询",
        history=[
            ConversationTurn(role="user", content=f"消息{i}")
            for i in range(5)
        ],
    )
    manager = ContextManager(
        max_messages=2,
        max_history_characters=100,
    )

    bundle = manager.build(state)

    assert [item.content for item in bundle.messages] == [
        "消息3",
        "消息4",
    ]
    assert bundle.original_message_count == 5
    assert bundle.selected_message_count == 2
    assert bundle.truncated is True


def test_context_preserves_working_facts() -> None:
    state = AgentState(
        title="退款",
        user_message="继续",
        intent="refund_or_return",
        entities={"order_id": "10001"},
        missing_fields=["refund_reason"],
    )

    bundle = ContextManager().build(state)
    history = bundle.decision_history()

    assert bundle.working_memory.active_goal == "refund_or_return"
    assert bundle.working_memory.known_facts == {
        "order_id": "10001"
    }
    assert bundle.working_memory.missing_information == [
        "refund_reason"
    ]
    assert history[0]["role"] == "system"
    assert "10001" in history[0]["content"]


def test_context_limits_tool_results() -> None:
    state = AgentState(
        title="工具测试",
        user_message="继续",
    )
    for index in range(5):
        state.record_tool_execution(
            tool_name="get_order",
            arguments={"order_id": str(index)},
            result={"success": True, "index": index},
        )

    bundle = ContextManager(max_tool_results=2).build(state)

    results = bundle.working_memory.important_tool_results
    assert len(results) == 2
    assert results[0]["result"]["index"] == 3
    assert results[1]["result"]["index"] == 4
    assert "tool_history" in bundle.sources


def test_context_metadata_survives_state_serialization() -> None:
    state = AgentState(
        title="上下文测试",
        user_message="当前消息",
        conversation_summary="用户正在查询订单。",
        context_metadata={
            "estimated_tokens": 120,
            "truncated": True,
        },
    )

    restored = AgentState.model_validate(
        state.model_dump(mode="json")
    )

    assert restored.conversation_summary == (
        "用户正在查询订单。"
    )
    assert restored.context_metadata["truncated"] is True


def test_context_summarizes_messages_removed_by_budget() -> None:
    state = AgentState(
        title="多轮咨询",
        user_message="最新问题",
        history=[
            ConversationTurn(role="user", content="旧问题一"),
            ConversationTurn(role="assistant", content="旧回答一"),
            ConversationTurn(role="user", content="最近问题"),
        ],
    )

    bundle = ContextManager(max_messages=1).build(state)

    assert bundle.truncated is True
    assert bundle.working_memory.conversation_summary is not None
    assert "用户: 旧问题一" in bundle.working_memory.conversation_summary
    assert "客服: 旧回答一" in bundle.working_memory.conversation_summary
    assert bundle.messages[0].content == "最近问题"
    assert "conversation_summary" in bundle.sources


def test_context_rolls_previous_summary_forward() -> None:
    state = AgentState(
        title="多轮咨询",
        user_message="继续",
        conversation_summary="用户之前咨询了订单。",
        history=[
            ConversationTurn(role="assistant", content="请提供订单号。"),
            ConversationTurn(role="user", content="订单号是10001"),
        ],
    )

    bundle = ContextManager(max_messages=1).build(state)
    summary = bundle.working_memory.conversation_summary

    assert summary is not None
    assert "用户之前咨询了订单。" in summary
    assert "客服: 请提供订单号。" in summary


def test_context_summary_is_bounded() -> None:
    state = AgentState(
        title="长对话",
        user_message="继续",
        history=[
            ConversationTurn(role="user", content="问题" * 300),
            ConversationTurn(role="assistant", content="回答" * 300),
        ],
    )

    bundle = ContextManager(max_messages=0).build(state)
    summary = bundle.working_memory.conversation_summary

    assert summary is not None
    assert len(summary) <= 1200


def test_context_does_not_summarize_same_messages_twice() -> None:
    state = AgentState(
        title="多轮咨询",
        user_message="继续",
        conversation_summary="用户: 已经摘要的问题",
        context_metadata={"summarized_message_count": 2},
        history=[
            ConversationTurn(role="user", content="已经摘要的问题"),
            ConversationTurn(role="assistant", content="已经摘要的回答"),
            ConversationTurn(role="user", content="最近问题"),
        ],
    )

    bundle = ContextManager(max_messages=1).build(state)

    assert bundle.working_memory.conversation_summary == (
        "用户: 已经摘要的问题"
    )
    assert bundle.summarized_message_count == 2


def test_context_includes_long_term_memory() -> None:
    state = AgentState(
        title="偏好咨询",
        user_message="继续",
        long_term_memories=[
            {
                "type": "preference",
                "content": "用户偏好：短信通知",
                "confidence": 1.0,
            }
        ],
    )

    bundle = ContextManager().build(state)
    history = bundle.decision_history()

    assert "long_term_memory" in bundle.sources
    assert "短信通知" in history[0]["content"]


def test_context_includes_retrieved_knowledge() -> None:
    state = AgentState(
        title="退款规则",
        user_message="多久可以退款",
        retrieved_knowledge=[
            {
                "chunk_id": 1,
                "title": "退款政策",
                "source": "policy/refund.md",
                "content": "未发货订单可申请退款。",
                "score": 5.0,
            }
        ],
    )

    bundle = ContextManager().build(state)
    history = bundle.decision_history()

    assert "knowledge_base" in bundle.sources
    assert "未发货订单可申请退款" in history[0]["content"]


def test_context_enforces_memory_and_knowledge_budgets() -> None:
    state = AgentState(
        title="预算测试",
        user_message="继续",
        long_term_memories=[
            {"content": "偏好" * 20},
            {"content": "旧偏好" * 20},
        ],
        retrieved_knowledge=[
            {
                "citation_id": "KB-1-v1",
                "title": "规则一",
                "content": "规则" * 20,
            },
            {
                "citation_id": "KB-2-v1",
                "title": "规则二",
                "content": "更多规则" * 20,
            },
        ],
    )
    bundle = ContextManager(
        max_memory_characters=80,
        max_knowledge_characters=100,
        max_context_characters=500,
    ).build(state)

    assert bundle.dropped_memory_count == 1
    assert bundle.dropped_knowledge_count == 1
    assert bundle.used_characters <= bundle.budget_characters
    assert "[KB-1-v1]" in bundle.decision_history()[0]["content"]
