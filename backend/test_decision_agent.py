import asyncio

from app.agent.decision import QwenDecisionAgent


async def main():

    agent = QwenDecisionAgent()

    result = await agent.decide(
        title="查询订单",
        content="帮我查一下订单10001",
        category="ORDER",
        intent="check_order",
    )

    print(result)


if __name__ == "__main__":
    asyncio.run(main())