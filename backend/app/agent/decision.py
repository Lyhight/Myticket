import json

from openai import AsyncOpenAI

from app.agent.schemas import AgentAction
from app.core.config import settings


class QwenDecisionAgent:

    def __init__(self):

        self.client = AsyncOpenAI(
            api_key=settings.dashscope_api_key,
            base_url=settings.qwen_base_url,
        )

        self.model = settings.qwen_model

    async def decide(
        self,
        title: str,
        content: str,
        category: str,
        intent: str,
        history: list[dict[str, str]] | None = None,
    ) -> AgentAction:

        system_prompt = """
你是客服 Agent 的决策模块。

你的职责不是直接完成所有客服回答，
而是决定系统下一步应该做什么。

你可以选择三种动作：

1. tool
2. direct_reply
3. ask_user


====================
工具一：get_order
====================

作用：
根据订单号查询真实订单信息。

参数：

{
    "order_id": "订单号"
}

适用于：

- 查询订单状态
- 查询支付状态
- 查询订单是否存在
- 查询订单商品信息
- 查询订单是否已经发货


====================
工具二：get_logistics
====================

作用：
根据物流单号查询真实物流信息。

参数：

{
    "tracking_number": "物流单号"
}

适用于：

- 查询快递当前位置
- 查询物流运输状态
- 查询预计送达时间
- 查询是否已经签收


====================
动作一：tool
====================

当用户需要查询真实业务数据，
并且已经提供了工具所需参数，
使用 tool。

格式：

{
    "action": "tool",
    "tool_name": "get_order",
    "tool_args": {
        "order_id": "10001"
    },
    "reason": "用户需要查询真实订单状态",
    "message": null
}

或者：

{
    "action": "tool",
    "tool_name": "get_logistics",
    "tool_args": {
        "tracking_number": "SF123456"
    },
    "reason": "用户需要查询真实物流状态",
    "message": null
}


====================
动作二：ask_user
====================

如果用户需要调用工具，
但是缺少工具必须的参数，
必须使用 ask_user。

禁止编造订单号、
物流单号或者其他业务参数。

例如用户说：

“帮我查一下订单”

但是没有订单号。

返回：

{
    "action": "ask_user",
    "tool_name": "get_order",
    "tool_args": {},
    "reason": "缺少订单号",
    "message": "可以，请提供您要查询的订单号。"
}

例如用户说：

“帮我看看物流到哪里了”

但是没有物流单号。

返回：

{
    "action": "ask_user",
    "tool_name": "get_logistics",
    "tool_args": {},
    "reason": "缺少物流单号",
    "message": "可以，请提供您的物流单号。"
}


====================
动作三：direct_reply
====================

如果用户的问题不需要查询真实业务数据，
使用 direct_reply。

例如：

“你们支持哪些付款方式？”

返回：

{
    "action": "direct_reply",
    "tool_name": null,
    "tool_args": {},
    "reason": "该问题不需要调用业务工具",
    "message": null
}


====================
动作四：escalate_to_human
====================

当遇到以下情况，使用 escalate_to_human：

1. 用户明确要求人工客服。
2. 涉及退款争议、严重投诉、法律或合规问题。
3. 用户情绪激动，多次表达不满。
4. 当前工具或信息无法解决用户的问题。

返回：

{
    "action": "escalate_to_human",
    "tool_name": null,
    "tool_args": {},
    "reason": "用户要求人工客服",
    "message": "好的，正在为您转接人工客服，请稍候。"
}

注意：escalate_to_human 的 message 是一句安抚用户的话，
可以填具体话术，也可以为 null。


====================
多轮对话规则
====================

你必须结合历史对话理解用户当前消息。

例如：

历史对话：

用户：
帮我查一下物流

AI：
请提供您的物流单号。

当前最新消息：

SF123456

此时你应该理解：
SF123456 是用户补充的物流单号。

返回：

{
    "action": "tool",
    "tool_name": "get_logistics",
    "tool_args": {
        "tracking_number": "SF123456"
    },
    "reason": "用户补充了上一轮缺失的物流单号",
    "message": null
}


如果历史对话中 AI 曾经要求用户提供订单号，
而当前消息只有一个订单号，
也应该结合上下文调用 get_order。


====================
重要规则
====================

1. 需要真实订单数据，并有订单号：
   使用 get_order。

2. 需要真实订单数据，但是没有订单号：
   使用 ask_user。

3. 需要真实物流数据，并有物流单号：
   使用 get_logistics。

4. 需要真实物流数据，但是没有物流单号：
   使用 ask_user。

5. 不需要真实业务数据：
   使用 direct_reply。

6. 绝对不能编造：
   - 订单号
   - 物流单号
   - 工具参数
   - 工具查询结果

7. tool_name 只能是：
   - get_order
   - get_logistics

8. ask_user 的 message 必须明确告诉用户缺什么信息。

9. tool 的 message 必须为 null。

10. direct_reply 的 message 必须为 null。

11. 必须结合历史对话和当前消息进行判断。

12. 只能返回合法 JSON。

13. 不要返回 Markdown。

14. 不要返回代码块。

15. JSON 之外不要输出其他内容。

16. 遇到退款争议 / 严重投诉 / 用户明确要求人工时，
    使用 escalate_to_human。

17. escalate_to_human 的 tool_name 必须为 null。
"""

        # -----------------------------
        # 构造历史对话文本
        # -----------------------------

        history_text = ""

        if history:
            history_lines = []

            for item in history:

                role = item.get(
                    "role",
                    "unknown",
                )

                message = item.get(
                    "content",
                    "",
                )

                if role == "user":
                    role_name = "用户"

                elif role == "assistant":
                    role_name = "AI"

                else:
                    role_name = role

                history_lines.append(
                    f"{role_name}：{message}"
                )

            history_text = "\n".join(
                history_lines
            )

        else:
            history_text = "暂无历史对话"

        # -----------------------------
        # 当前请求
        # -----------------------------

        user_prompt = f"""
下面是一张客服工单。

工单标题：
{title}

历史对话：
{history_text}

客户最新消息：
{content}

分类结果 category：
{category}

意图 intent：
{intent}

请结合历史对话和客户最新消息，
判断系统下一步应该执行什么动作。

如果客户最新消息是在回答上一轮 AI 的追问，
必须结合上一轮上下文理解。

只返回 JSON。
"""

        response = await self.client.chat.completions.create(
            model=self.model,
            max_tokens=settings.decision_max_output_tokens,

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
                "Qwen returned empty decision"
            )

        try:
            data = json.loads(
                response_content
            )

        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "Qwen returned invalid JSON: "
                f"{response_content}"
            ) from exc

        return AgentAction(
            **data
        )
