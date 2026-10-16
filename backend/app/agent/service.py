import logging
from time import perf_counter

from app.agent.classifier import (
    QwenTicketClassifier,
    RuleBasedTicketClassifier,
)

from app.agent.runtime import AgentRuntime

from app.agent.schemas import (
    TicketClassification,
)
from app.agent.schemas import ClassificationExecution
from app.core.config import settings

logger = logging.getLogger(__name__)


class TicketClassificationService:
    """
    工单分类 Agent 服务层

    负责:
    1. 创建 Agent Runtime
    2. 调用 Qwen
    3. 失败时 fallback
    4. 返回最终分类结果
    """

    def __init__(self):

        # 主模型
        self.rule_classifier = RuleBasedTicketClassifier()
        self.runtime = (
            AgentRuntime(
                primary_classifier=QwenTicketClassifier(),
                fallback_classifier=self.rule_classifier,
                timeout_seconds=settings.classification_timeout_seconds,
                max_retries=settings.classification_max_retries,
                retry_delay_seconds=settings.llm_retry_delay_seconds,
            )
            if settings.llm_enabled
            else None
        )
    async def classify(
        self,
        title: str,
        content: str,
    ) -> ClassificationExecution:

        if self.runtime is None:
            started = perf_counter()
            classification = await self.rule_classifier.classify(
                title=title,
                content=content,
            )
            execution = ClassificationExecution(
                classification=classification,
                source="rule_based",
                fallback_used=False,
                attempts=1,
                latency_ms=(perf_counter() - started) * 1000,
            )
        else:
            execution = await self.runtime.run(
                title=title,
                content=content,
            )

        logger.info(
            "Ticket classified: "
            "source=%s, "
            "fallback=%s, "
            "attempts=%s, "
            "latency_ms=%.2f",
            execution.source,
            execution.fallback_used,
            execution.attempts,
            execution.latency_ms,
        )

        return execution
