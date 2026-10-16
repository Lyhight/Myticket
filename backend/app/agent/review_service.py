import logging
from typing import Any

from app.agent.retry import run_with_retry
from app.agent.review import (
    QwenReplyReviewer,
    RuleBasedReplyReviewer,
)
from app.agent.schemas import ReviewResult
from app.core.config import settings


logger = logging.getLogger(__name__)

class ReplyReviewService:
    """
    回复复核服务层：

    1. 优先用 Qwen 复核
    2. Qwen 失败时降级为规则复核
    3. 返回最终复核结论
    """

    def __init__(self):

        self.primary = QwenReplyReviewer() if settings.llm_enabled else None

        self.fallback = RuleBasedReplyReviewer()

    async def review(
        self,
        reply: str,
        title: str,
        content: str,
        category: str,
        intent: str,
        tool_result: dict[str, Any] | None = None,
    ) -> ReviewResult:

        deterministic_review = await self.fallback.review(
            reply=reply,
            title=title,
            content=content,
            category=category,
            intent=intent,
            tool_result=tool_result,
        )
        if not deterministic_review.approved:
            return deterministic_review
        if self.primary is None:
            return deterministic_review

        try:
            return await run_with_retry(
                lambda: self.primary.review(
                    reply=reply,
                    title=title,
                    content=content,
                    category=category,
                    intent=intent,
                    tool_result=tool_result,
                ),
                timeout_seconds=settings.review_timeout_seconds,
                max_retries=settings.review_max_retries,
                retry_delay_seconds=settings.llm_retry_delay_seconds,
            )

        except Exception:
            logger.exception(
                "Qwen reply review failed, "
                "falling back to rule-based review"
            )

            return deterministic_review
