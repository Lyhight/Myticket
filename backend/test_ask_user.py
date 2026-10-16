import asyncio

from app.agent.customer_service_agent import (
    CustomerServiceAgent,
)


async def main():

    agent = CustomerServiceAgent()

    result = await agent.run(
        title="查询物流",
        content="物流单号SF123456，现在到哪里了？",
    )

    print("\nClassification:")
    print(
        result
        .classification_execution
        .classification
    )

    print("\nAction:")
    print(
        result.action
    )

    print("\nTool Result:")
    print(
        result.tool_result
    )

    print("\nReply:")
    print(
        result.reply
    )


if __name__ == "__main__":
    asyncio.run(main())