from abc import ABC, abstractmethod
import json

from openai import AsyncOpenAI

from app.agent.prompts import (
    TICKET_CLASSIFICATION_SYSTEM_PROMPT,
)
from app.agent.schemas import TicketClassification
from app.core.config import settings


class BaseTicketClassifier(ABC):

    @abstractmethod
    async def classify(
        self,
        title: str,
        content: str,
    ) -> TicketClassification:
        pass


class RuleBasedTicketClassifier(
    BaseTicketClassifier
):

    async def classify(
        self,
        title: str,
        content: str,
    ) -> TicketClassification:

        text = f"{title} {content}".lower()
        urgent = any(
            keyword in text
            for keyword in [
                "盗刷",
                "被盗",
                "泄露",
                "冻结",
                "丢失",
                "诈骗",
                "紧急",
            ]
        )

        # 售后动作优先于物流描述，避免“已签收但要退款”被物流词截获。
        if any(
            keyword in text
            for keyword in [
                "退款",
                "退货",
                "换货",
                "售后",
            ]
        ):
            return TicketClassification(
                category="REFUND",
                priority="URGENT" if urgent else "HIGH",
                intent="refund_or_return",
                route_to="after_sales",
            )

        if any(
            keyword in text
            for keyword in [
                "发货",
                "物流",
                "快递",
                "配送",
                "签收",
                "运输",
                "包裹",
            ]
        ):
            return TicketClassification(
                category="LOGISTICS",
                priority="URGENT" if urgent else "NORMAL",
                intent="shipping_issue",
                route_to="logistics_support",
            )

        if any(
            keyword in text
            for keyword in [
                "优惠券",
                "优惠",
                "折扣",
                "活动",
            ]
        ):
            return TicketClassification(
                category="COUPON",
                priority="NORMAL",
                intent="coupon_issue",
                route_to="marketing_support",
            )

        if any(
            keyword in text
            for keyword in [
                "登录",
                "密码",
                "账号",
                "账户",
            ]
        ):
            return TicketClassification(
                category="ACCOUNT",
                priority="URGENT" if urgent else "NORMAL",
                intent="account_issue",
                route_to="account_support",
            )

        if any(
            keyword in text
            for keyword in [
                "订单",
                "支付",
                "付款",
                "取消订单",
            ]
        ):
            return TicketClassification(
                category="ORDER",
                priority="URGENT" if urgent else "NORMAL",
                intent="order_issue",
                route_to="order_support",
            )

        if any(
            keyword in text
            for keyword in [
                "产品",
                "商品",
                "质量",
                "怎么用",
                "使用",
            ]
        ):
            return TicketClassification(
                category="PRODUCT",
                priority="NORMAL",
                intent="product_issue",
                route_to="product_support",
            )

        return TicketClassification(
            category="OTHER",
            priority="LOW",
            intent="general_question",
            route_to="general_support",
        )


class QwenTicketClassifier(
    BaseTicketClassifier
):

    def __init__(self):

        self.client = AsyncOpenAI(
            api_key=settings.dashscope_api_key,
            base_url=settings.qwen_base_url,
        )

        self.model = settings.qwen_model

    async def classify(
        self,
        title: str,
        content: str,
    ) -> TicketClassification:

        user_prompt = f"""
工单标题：
{title}

客户消息：
{content}

请根据系统规则对这个工单进行分类。
"""

        response = await self.client.chat.completions.create(
            model=self.model,
            max_tokens=settings.classification_max_output_tokens,

            messages=[
                {
                    "role": "system",
                    "content": (
                        TICKET_CLASSIFICATION_SYSTEM_PROMPT
                    ),
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],

            response_format={
                "type": "json_object",
            },
        )

        response_content = (
            response
            .choices[0]
            .message
            .content
        )

        if not response_content:
            raise RuntimeError(
                "Qwen returned empty response"
            )

        data = json.loads(
            response_content
        )

        return TicketClassification(
            **data
        )
