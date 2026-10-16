import asyncio
import logging
import time

from app.agent.classifier import (
    BaseTicketClassifier,
)
from app.agent.schemas import (
    ClassificationExecution,
)


logger = logging.getLogger(__name__)


class AgentRuntime:

    def __init__(
        self,
        primary_classifier: BaseTicketClassifier,
        fallback_classifier: BaseTicketClassifier,
        timeout_seconds: float = 15.0,
        max_retries: int = 2,
        retry_delay_seconds: float = 1.0,
    ):
        self.primary_classifier = (
            primary_classifier
        )

        self.fallback_classifier = (
            fallback_classifier
        )

        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.retry_delay_seconds = (
            retry_delay_seconds
        )

    async def run(
        self,
        title: str,
        content: str,
    ) -> ClassificationExecution:

        start_time = time.perf_counter()

        attempts = 0
        last_error: Exception | None = None

        # 初次调用 + retry
        total_attempts = self.max_retries + 1

        for attempt in range(
            1,
            total_attempts + 1,
        ):
            attempts = attempt

            try:
                logger.info(
                    "Calling Qwen classifier, "
                    "attempt=%s",
                    attempt,
                )

                classification = (
                    await asyncio.wait_for(
                        self.primary_classifier.classify(
                            title=title,
                            content=content,
                        ),
                        timeout=self.timeout_seconds,
                    )
                )

                latency_ms = (
                    time.perf_counter()
                    - start_time
                ) * 1000

                logger.info(
                    "Qwen classification succeeded, "
                    "attempt=%s, latency_ms=%.2f",
                    attempt,
                    latency_ms,
                )

                return ClassificationExecution(
                    classification=classification,
                    source="qwen",
                    fallback_used=False,
                    attempts=attempts,
                    latency_ms=latency_ms,
                )

            except asyncio.TimeoutError as exc:
                last_error = exc

                logger.warning(
                    "Qwen classification timeout, "
                    "attempt=%s",
                    attempt,
                )

            except Exception as exc:
                last_error = exc

                logger.warning(
                    "Qwen classification failed, "
                    "attempt=%s, error=%s",
                    attempt,
                    exc,
                )

            # 如果还有重试机会
            if attempt < total_attempts:

                delay = (
                    self.retry_delay_seconds
                    * (2 ** (attempt - 1))
                )

                logger.info(
                    "Retrying Qwen after %.1f seconds",
                    delay,
                )

                await asyncio.sleep(delay)

        # -------------------------
        # Qwen 多次失败
        # 使用规则分类器兜底
        # -------------------------

        logger.error(
            "Qwen failed after %s attempts. "
            "Using rule-based fallback. "
            "Last error: %s",
            attempts,
            last_error,
        )

        classification = (
            await self.fallback_classifier.classify(
                title=title,
                content=content,
            )
        )

        latency_ms = (
            time.perf_counter()
            - start_time
        ) * 1000

        return ClassificationExecution(
            classification=classification,
            source="rule_based",
            fallback_used=True,
            attempts=attempts,
            latency_ms=latency_ms,
        )