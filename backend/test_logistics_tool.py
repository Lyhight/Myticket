import asyncio

from app.tools.logistics_tools import (
    get_logistics,
)


async def main():

    result = await get_logistics(
        tracking_number="SF123456"
    )

    print(result)


if __name__ == "__main__":
    asyncio.run(main())