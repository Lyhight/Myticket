import pytest

from app.agent.review import (
    RuleBasedReplyReviewer,
)


async def review_reply(reply: str):
    reviewer = RuleBasedReplyReviewer()

    return await reviewer.review(
        reply=reply,
        title="测试工单",
        content="请帮我查询订单",
        category="ORDER",
        intent="order_query",
        tool_result=None,
    )


async def test_normal_reply_is_approved() -> None:
    result = await review_reply(
        "您好，已经收到您的问题，请提供订单号以便查询。"
    )

    assert result.approved is True
    assert result.issues == []


async def test_empty_reply_is_rejected() -> None:
    result = await review_reply("")

    assert result.approved is False
    assert "回复为空" in result.issues


async def test_whitespace_reply_is_rejected() -> None:
    result = await review_reply("   ")

    assert result.approved is False
    assert "回复为空" in result.issues


async def test_short_reply_is_rejected() -> None:
    result = await review_reply("好的")

    assert result.approved is False
    assert "回复过短" in result.issues


@pytest.mark.parametrize(
    "internal_term",
    [
        "category",
        "intent",
        "route_to",
        "tool_name",
        "tool_result",
        "classification",
        "agent_run",
    ],
)
async def test_internal_fields_are_rejected(
    internal_term: str,
) -> None:
    result = await review_reply(
        f"内部处理信息包含 {internal_term} 字段，请稍候。"
    )

    assert result.approved is False
    assert any(
        internal_term in issue
        for issue in result.issues
    )


async def test_internal_fields_are_case_insensitive() -> None:
    result = await review_reply(
        "内部 CATEGORY 字段已经完成处理。"
    )

    assert result.approved is False
    assert any(
        "category" in issue
        for issue in result.issues
    )