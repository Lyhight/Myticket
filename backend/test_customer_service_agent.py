import asyncio

from app.agent.customer_service_agent import (
    CustomerServiceAgent,
)


async def main():

    agent = CustomerServiceAgent()

    result = await agent.run(
        title="订单为什么还没有发货",
        content=(
            "我的订单10001已经付款，"
            "但是一直没有发货。"
        ),
    )

    print()
    print("=" * 60)
    print("Customer Service Agent Result")
    print("=" * 60)

    print()
    print("【分类】")
    print(
        result
        .classification_execution
        .classification
    )

    print()
    print("【执行来源】")
    print(
        result
        .classification_execution
        .source
    )

    print()
    print("【决策】")
    print(
        result.action
    )

    print()
    print("【工具结果】")
    print(
        result.tool_result
    )

    print()
    print("【最终回复】")
    print(
        result.reply
    )


if __name__ == "__main__":
    asyncio.run(main())