import asyncio
import hashlib
import math
import secrets
from collections import defaultdict, deque
from time import monotonic
from typing import Any

from fastapi import HTTPException, status

from app.core.config import settings


_REDIS_SLIDING_WINDOW_SCRIPT = """
local current = redis.call('TIME')
local now = current[1] * 1000 + math.floor(current[2] / 1000)
local window = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now - window)
local count = redis.call('ZCARD', KEYS[1])
if count >= limit then
    local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
    local retry = window
    if oldest[2] then
        retry = math.max(1, tonumber(oldest[2]) + window - now)
    end
    return {0, retry}
end
redis.call('ZADD', KEYS[1], now, tostring(now) .. '-' .. ARGV[3])
redis.call('PEXPIRE', KEYS[1], window)
return {limit - count - 1, 0}
"""

_redis_client: Any | None = None


def _redis_error_type() -> type[Exception]:
    try:
        from redis.exceptions import RedisError
    except ImportError:
        return RuntimeError
    return RedisError


def get_rate_limit_redis_client() -> Any:
    global _redis_client
    if _redis_client is None:
        try:
            from redis.asyncio import Redis
        except ImportError as exc:
            raise RuntimeError(
                "Redis rate limiting requires the 'redis' package"
            ) from exc
        _redis_client = Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=2,
            socket_timeout=2,
            health_check_interval=30,
        )
    return _redis_client


async def close_rate_limit_backend() -> None:
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None


async def check_rate_limit_backend() -> str:
    if settings.rate_limit_backend == "memory":
        return "memory"
    await get_rate_limit_redis_client().ping()
    return "redis"


class SlidingWindowRateLimiter:
    """进程内滑动窗口；接口隔离后可替换为 Redis 实现。"""

    def __init__(
        self,
        *,
        limit: int,
        window_seconds: float,
        detail: str = "Request rate limit exceeded",
    ) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.detail = detail
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def consume(self, key: str) -> int:
        now = monotonic()
        boundary = now - self.window_seconds
        async with self._lock:
            events = self._events[key]
            while events and events[0] <= boundary:
                events.popleft()
            if len(events) >= self.limit:
                retry_after = max(1, int(events[0] + self.window_seconds - now) + 1)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=self.detail,
                    headers={"Retry-After": str(retry_after)},
                )
            events.append(now)
            return self.limit - len(events)

    def reset(self) -> None:
        self._events.clear()


class RedisSlidingWindowRateLimiter:
    """Redis-backed atomic sliding window with configurable local fallback."""

    def __init__(
        self,
        *,
        limit: int,
        window_seconds: float,
        detail: str = "Request rate limit exceeded",
        redis_client: Any | None = None,
        failure_mode: str = "local",
        key_prefix: str | None = None,
    ) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.detail = detail
        self.redis = (
            redis_client
            if redis_client is not None
            else get_rate_limit_redis_client()
        )
        self.failure_mode = failure_mode
        self.key_prefix = key_prefix or settings.rate_limit_key_prefix
        self.local_fallback = SlidingWindowRateLimiter(
            limit=limit,
            window_seconds=window_seconds,
            detail=detail,
        )

    def _key(self, key: str) -> str:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return f"{self.key_prefix}:{digest}"

    async def consume(self, key: str) -> int:
        try:
            result = await self.redis.eval(
                _REDIS_SLIDING_WINDOW_SCRIPT,
                1,
                self._key(key),
                max(1, int(self.window_seconds * 1000)),
                self.limit,
                secrets.token_hex(8),
            )
        except _redis_error_type() as exc:
            if self.failure_mode == "local":
                return await self.local_fallback.consume(key)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Rate limit service unavailable",
            ) from exc

        remaining, retry_ms = int(result[0]), int(result[1])
        if retry_ms > 0:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=self.detail,
                headers={
                    "Retry-After": str(max(1, math.ceil(retry_ms / 1000)))
                },
            )
        return remaining

    def reset(self) -> None:
        self.local_fallback.reset()


def create_rate_limiter(
    *,
    limit: int,
    window_seconds: float,
    detail: str = "Request rate limit exceeded",
) -> SlidingWindowRateLimiter | RedisSlidingWindowRateLimiter:
    if settings.rate_limit_backend == "redis":
        return RedisSlidingWindowRateLimiter(
            limit=limit,
            window_seconds=window_seconds,
            detail=detail,
            failure_mode=settings.rate_limit_redis_failure_mode,
        )
    return SlidingWindowRateLimiter(
        limit=limit,
        window_seconds=window_seconds,
        detail=detail,
    )
