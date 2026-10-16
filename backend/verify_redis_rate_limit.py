"""Small deployment smoke test for the real Redis rate-limit backend."""

import asyncio
from uuid import uuid4

from fastapi import HTTPException

from app.operations.rate_limit import (
    RedisSlidingWindowRateLimiter,
    close_rate_limit_backend,
    get_rate_limit_redis_client,
)


async def main() -> None:
    client = get_rate_limit_redis_client()
    raw_key = f"deployment-smoke:{uuid4().hex}"
    limiter = RedisSlidingWindowRateLimiter(
        limit=1,
        window_seconds=10,
        redis_client=client,
    )
    redis_key = limiter._key(raw_key)
    try:
        remaining = await limiter.consume(raw_key)
        if remaining != 0:
            raise RuntimeError("Unexpected Redis rate-limit remainder")
        try:
            await limiter.consume(raw_key)
        except HTTPException as exc:
            if exc.status_code != 429:
                raise
        else:
            raise RuntimeError("Redis rate limit did not reject excess request")
        print("redis rate-limit smoke: ok")
    finally:
        await client.delete(redis_key)
        await close_rate_limit_backend()


if __name__ == "__main__":
    asyncio.run(main())
