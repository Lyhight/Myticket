from abc import ABC, abstractmethod
from typing import Any

from openai import AsyncOpenAI

from app.core.config import settings


class BaseReplyGenerator(ABC):

    @abstractmethod
    async def generate_reply(
        self,
        title: str,
        content: str,
        category: str,
        priority: str,
        intent: str,
        tool_result: dict[str, Any] | None = None,
        knowledge_context: list[dict[str, Any]] | None = None,
    ) -> str:
        pass


class QwenReplyGenerator(
    BaseReplyGenerator
):

    def __init__(self):

        self.client = AsyncOpenAI(
            api_key=settings.dashscope_api_key,
            base_url=settings.qwen_base_url,
        )

        self.model = settings.qwen_model

    async def generate_reply(
        self,
        title: str,
        content: str,
        category: str,
        priority: str,
        intent: str,
        tool_result: dict[str, Any] | None = None,
        knowledge_context: list[dict[str, Any]] | None = None,
    ) -> str:

        system_prompt = """
你是一个电商客服智能助手。

你的任务是根据客户工单以及系统提供的真实业务数据，
生成简洁、专业、友好的客服回复。

必须遵守以下规则：

1. 不允许编造订单状态。
2. 不允许编造物流信息。
3. 不允许编造退款状态。
4. 如果提供了工具查询结果，必须以工具结果为事实依据。
5. 如果没有真实业务数据，不要假装已经查询。
6. 不要向客户暴露内部 category、intent、tool 等技术信息。
7. 只输出客服回复正文。
8. 回答规则、政策、流程类问题时，优先依据知识库检索结果。
9. 知识库没有相关内容时，不得编造公司政策。
10. 工具结果代表实时业务数据，优先级高于知识库内容。
"""

        user_prompt = f"""
工单标题：
{title}

客户消息：
{content}

工单类别：
{category}

优先级：
{priority}

客户意图：
{intent}

工具查询结果：
{tool_result}

知识库检索结果：
{knowledge_context}

请根据这些信息生成客服回复。
"""

        response = (
            await self.client
            .chat.completions
            .create(
                model=self.model,
                max_tokens=settings.reply_max_output_tokens,

                messages=[
                    {
                        "role": "system",
                        "content": system_prompt,
                    },
                    {
                        "role": "user",
                        "content": user_prompt,
                    },
                ],
            )
        )

        reply = (
            response
            .choices[0]
            .message
            .content
        )

        if not reply:
            raise RuntimeError(
                "Qwen returned empty reply"
            )

        return reply.strip()
