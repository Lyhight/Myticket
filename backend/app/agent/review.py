import json
from abc import ABC, abstractmethod
from typing import Any

from openai import AsyncOpenAI

from app.agent.schemas import ReviewResult
from app.core.config import settings
from app.agent.guardrails import PrivacyGuard


class BaseReplyReviewer(ABC):

    @abstractmethod
    async def review(
        self,
        reply: str,
        title: str,
        content: str,
        category: str,
        intent: str,
        tool_result: dict[str, Any] | None = None,
    ) -> ReviewResult:
        pass


class RuleBasedReplyReviewer(BaseReplyReviewer):
    """规则复核：不依赖 LLM，检查明显违规。"""

    BANNED_TERMS = [
        "category",
        "intent",
        "route_to",
        "tool_name",
        "tool_result",
        "classification",
        "agent_run",
    ]

    async def review(
        self,
        reply: str,
        title: str,
        content: str,
        category: str,
        intent: str,
        tool_result: dict[str, Any] | None = None,
    ) -> ReviewResult:

        issues: list[str] = []

        lowered = reply.lower()

        for term in self.BANNED_TERMS:
            if term in lowered:
                issues.append(
                    f"回复泄露了内部字段: {term}"
                )

        issues.extend(PrivacyGuard.issues(reply))

        if not reply.strip():
            issues.append("回复为空")

        elif len(reply.strip()) < 5:
            issues.append("回复过短")

        if len(reply) > 4_000:
            issues.append("回复过长")

        return ReviewResult(
            approved=len(issues) == 0,
            issues=issues,
        )


class QwenReplyReviewer(BaseReplyReviewer):

    def __init__(self):

        self.client = AsyncOpenAI(
            api_key=settings.dashscope_api_key,
            base_url=settings.qwen_base_url,
        )

        self.model = settings.qwen_model

    async def review(
        self,
        reply: str,
        title: str,
        content: str,
        category: str,
        intent: str,
        tool_result: dict[str, Any] | None = None,
    ) -> ReviewResult:

        system_prompt = """
你是客服回复的复核员（reviewer）。

你的任务是判断下面这条 AI 客服回复是否合规、安全、可以发给客户。

检查维度：

1. 是否编造了订单 / 物流 / 退款等业务事实，
   尤其是工具查询结果里根本没有的信息。
2. 是否向客户泄露了内部技术字段
   （category、intent、route_to、tool、agent、分类等）。
3. 是否把"查询失败 / 未找到 / 内部错误"直接暴露给客户。
4. 语气是否专业、礼貌。
5. 回复是否为空或明显不完整。

只返回 JSON，格式：

{"approved": true, "issues": []}

或者：

{"approved": false, "issues": ["编造了不存在的物流状态"]}

规则：

1. approved 为 false 时，issues 必须列出具体问题。
2. approved 为 true 时，issues 必须为空数组。
3. 只返回 JSON，不要 Markdown，不要代码块。
4. JSON 之外不要输出任何内容。
"""

        user_prompt = f"""
工单标题：
{title}

客户消息：
{content}

工单类别：
{category}

客户意图：
{intent}

工具查询结果：
{tool_result}

待复核的客服回复：
{reply}

请复核并返回 JSON。
"""

        response = await self.client.chat.completions.create(
            model=self.model,
            max_tokens=settings.review_max_output_tokens,

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
                "Qwen returned empty review"
            )

        data = json.loads(response_content)

        approved = data.get("approved")

        if not isinstance(approved, bool):
            raise RuntimeError(
                "Reviewer returned non-bool approved: "
                f"{approved!r}"
            )

        issues = data.get("issues", [])

        if isinstance(issues, str):
            issues = [issues]

        elif not isinstance(issues, list):
            issues = []

        return ReviewResult(
            approved=approved,
            issues=issues,
        )
