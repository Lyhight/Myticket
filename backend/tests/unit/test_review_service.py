from unittest.mock import AsyncMock, Mock

from app.agent.review_service import ReplyReviewService
from app.agent.schemas import ReviewResult


async def test_deterministic_privacy_rejection_cannot_be_overridden() -> None:
    service = ReplyReviewService.__new__(ReplyReviewService)
    service.fallback = Mock()
    service.fallback.review = AsyncMock(
        return_value=ReviewResult(
            approved=False,
            issues=["可能包含银行卡号"],
        )
    )
    service.primary = Mock()
    service.primary.review = AsyncMock(
        return_value=ReviewResult(approved=True, issues=[]),
    )

    result = await service.review(
        reply="您的银行卡号是6222021234567890123",
        title="退款",
        content="查询退款",
        category="REFUND",
        intent="refund_status",
    )

    assert result.approved is False
    service.primary.review.assert_not_awaited()
