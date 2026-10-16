import asyncio

from app.agent.classifier import (
    BaseTicketClassifier,
)
from app.agent.runtime import AgentRuntime
from app.agent.schemas import TicketClassification


def make_classification(
    category: str = "ORDER",
) -> TicketClassification:
    return TicketClassification(
        category=category,
        priority="NORMAL",
        intent="order_query",
        route_to="order_support",
    )


class FixedClassifier(BaseTicketClassifier):

    def __init__(
        self,
        classification: TicketClassification,
    ) -> None:
        self.classification = classification
        self.calls = 0

    async def classify(
        self,
        title: str,
        content: str,
    ) -> TicketClassification:
        self.calls += 1
        return self.classification


class FailingClassifier(BaseTicketClassifier):

    def __init__(self) -> None:
        self.calls = 0

    async def classify(
        self,
        title: str,
        content: str,
    ) -> TicketClassification:
        self.calls += 1
        raise RuntimeError("model unavailable")


class FlakyClassifier(BaseTicketClassifier):

    def __init__(
        self,
        succeed_on_attempt: int,
    ) -> None:
        self.succeed_on_attempt = succeed_on_attempt
        self.calls = 0

    async def classify(
        self,
        title: str,
        content: str,
    ) -> TicketClassification:
        self.calls += 1

        if self.calls < self.succeed_on_attempt:
            raise RuntimeError("temporary model error")

        return make_classification()


class SlowClassifier(BaseTicketClassifier):

    def __init__(self) -> None:
        self.calls = 0

    async def classify(
        self,
        title: str,
        content: str,
    ) -> TicketClassification:
        self.calls += 1
        await asyncio.sleep(0.05)
        return make_classification()


async def test_primary_classifier_success() -> None:
    primary = FixedClassifier(
        make_classification(),
    )
    fallback = FixedClassifier(
        make_classification("OTHER"),
    )

    runtime = AgentRuntime(
        primary_classifier=primary,
        fallback_classifier=fallback,
        timeout_seconds=1,
        max_retries=2,
        retry_delay_seconds=0,
    )

    result = await runtime.run(
        title="查询订单",
        content="订单10001现在是什么状态",
    )

    assert result.source == "qwen"
    assert result.fallback_used is False
    assert result.attempts == 1
    assert result.classification.category == "ORDER"
    assert result.latency_ms >= 0
    assert primary.calls == 1
    assert fallback.calls == 0


async def test_primary_retries_then_succeeds() -> None:
    primary = FlakyClassifier(
        succeed_on_attempt=2,
    )
    fallback = FixedClassifier(
        make_classification("OTHER"),
    )

    runtime = AgentRuntime(
        primary_classifier=primary,
        fallback_classifier=fallback,
        timeout_seconds=1,
        max_retries=2,
        retry_delay_seconds=0,
    )

    result = await runtime.run(
        title="查询订单",
        content="查询订单状态",
    )

    assert result.source == "qwen"
    assert result.fallback_used is False
    assert result.attempts == 2
    assert primary.calls == 2
    assert fallback.calls == 0


async def test_primary_failure_uses_fallback() -> None:
    primary = FailingClassifier()
    fallback = FixedClassifier(
        make_classification("OTHER"),
    )

    runtime = AgentRuntime(
        primary_classifier=primary,
        fallback_classifier=fallback,
        timeout_seconds=1,
        max_retries=2,
        retry_delay_seconds=0,
    )

    result = await runtime.run(
        title="无法分类的问题",
        content="测试内容",
    )

    assert result.source == "rule_based"
    assert result.fallback_used is True
    assert result.attempts == 3
    assert result.classification.category == "OTHER"
    assert primary.calls == 3
    assert fallback.calls == 1


async def test_primary_timeout_uses_fallback() -> None:
    primary = SlowClassifier()
    fallback = FixedClassifier(
        make_classification("OTHER"),
    )

    runtime = AgentRuntime(
        primary_classifier=primary,
        fallback_classifier=fallback,
        timeout_seconds=0.01,
        max_retries=0,
        retry_delay_seconds=0,
    )

    result = await runtime.run(
        title="超时测试",
        content="测试模型超时后的降级",
    )

    assert result.source == "rule_based"
    assert result.fallback_used is True
    assert result.attempts == 1
    assert result.classification.category == "OTHER"
    assert primary.calls == 1
    assert fallback.calls == 1