import logging
from typing import Any

from app.agent.reply import (
    QwenReplyGenerator,
)
from app.agent.retry import run_with_retry
from app.core.config import settings


logger = logging.getLogger(__name__)

class AutoReplyService:

    def __init__(self):

        self.generator = QwenReplyGenerator() if settings.llm_enabled else None

    async def generate(
        self,
        title: str,
        content: str,
        category: str,
        priority: str,
        intent: str,
        tool_result: dict[str, Any] | None = None,
        knowledge_context: list[dict[str, Any]] | None = None,
    ) -> str:

        if self.generator is None:
            return self._offline_reply(tool_result, knowledge_context)

        try:

            return await run_with_retry(
                lambda: self.generator.generate_reply(
                    title=title,
                    content=content,
                    category=category,
                    priority=priority,
                    intent=intent,
                    tool_result=tool_result,
                    knowledge_context=knowledge_context,
                ),
                timeout_seconds=settings.reply_timeout_seconds,
                max_retries=settings.reply_max_retries,
                retry_delay_seconds=settings.llm_retry_delay_seconds,
            )

        except Exception:

            logger.exception(
                "Qwen auto reply failed"
            )

            return (
                "您好，您的问题已经收到。"
                "目前我们正在进一步核实相关情况，"
                "请您稍后留意处理进展。"
            )

    @staticmethod
    def _offline_reply(
        tool_result: dict[str, Any] | None,
        knowledge_context: list[dict[str, Any]] | None,
    ) -> str:
        if tool_result and tool_result.get("success"):
            order = tool_result.get("order")
            if isinstance(order, dict):
                return (
                    f"您好，订单{order.get('order_id', '')}当前状态为"
                    f"{order.get('status', '未知')}，物流状态为"
                    f"{order.get('shipping_status', '未知')}。"
                )
            logistics = tool_result.get("logistics")
            if isinstance(logistics, dict):
                return (
                    f"您好，物流单{logistics.get('tracking_number', '')}"
                    f"当前状态为{logistics.get('status', '未知')}，"
                    f"当前位置：{logistics.get('current_location') or '暂无'}。"
                )
        if knowledge_context:
            content = str(knowledge_context[0].get("content", "")).strip()
            if content:
                return f"您好，根据相关规则：{content[:500]}"
        return (
            "您好，您的问题已经收到。当前为离线规则模式，"
            "如需进一步核实业务信息，请联系人工客服。"
        )
