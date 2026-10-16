import pytest
from fastapi import HTTPException

from app.operations.metrics import AgentOperationsService
from app.operations import rate_limit
from app.operations.rate_limit import (
    RedisSlidingWindowRateLimiter,
    SlidingWindowRateLimiter,
)


class FakeRedis:
    def __init__(self, *results) -> None:
        self.results = list(results)
        self.calls = []

    async def eval(self, *args):
        self.calls.append(args)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


async def test_rate_limiter_rejects_excess_requests() -> None:
    limiter = SlidingWindowRateLimiter(limit=2, window_seconds=60)
    assert await limiter.consume("user:1") == 1
    assert await limiter.consume("user:1") == 0
    with pytest.raises(HTTPException) as exc:
        await limiter.consume("user:1")
    assert exc.value.status_code == 429
    assert exc.value.headers["Retry-After"]


async def test_redis_rate_limiter_uses_anonymous_atomic_key() -> None:
    redis = FakeRedis([1, 0], [0, 1500])
    limiter = RedisSlidingWindowRateLimiter(
        limit=2,
        window_seconds=60,
        redis_client=redis,
        key_prefix="test:limit",
    )

    assert await limiter.consume("account:private@example.com") == 1
    with pytest.raises(HTTPException) as exc:
        await limiter.consume("account:private@example.com")

    redis_key = redis.calls[0][2]
    assert redis_key.startswith("test:limit:")
    assert "private@example.com" not in redis_key
    assert exc.value.status_code == 429
    assert exc.value.headers["Retry-After"] == "2"


async def test_redis_rate_limiter_can_fallback_locally(monkeypatch) -> None:
    class FakeRedisError(Exception):
        pass

    monkeypatch.setattr(
        rate_limit,
        "_redis_error_type",
        lambda: FakeRedisError,
    )
    limiter = RedisSlidingWindowRateLimiter(
        limit=1,
        window_seconds=60,
        redis_client=FakeRedis(FakeRedisError("offline")),
        failure_mode="local",
    )

    assert await limiter.consume("user:1") == 0


async def test_redis_rate_limiter_can_fail_closed(monkeypatch) -> None:
    class FakeRedisError(Exception):
        pass

    monkeypatch.setattr(
        rate_limit,
        "_redis_error_type",
        lambda: FakeRedisError,
    )
    limiter = RedisSlidingWindowRateLimiter(
        limit=1,
        window_seconds=60,
        redis_client=FakeRedis(FakeRedisError("offline")),
        failure_mode="deny",
    )

    with pytest.raises(HTTPException) as exc:
        await limiter.consume("user:1")
    assert exc.value.status_code == 503


def test_alert_thresholds() -> None:
    alerts = AgentOperationsService.alerts({
        "run_count": 10,
        "failure_rate": 0.3,
        "escalation_rate": 0.6,
        "p95_latency_ms": 12000,
        "tool_failure_count": 3,
    })
    assert {item["code"] for item in alerts} == {
        "HIGH_FAILURE_RATE",
        "HIGH_ESCALATION_RATE",
        "HIGH_P95_LATENCY",
        "TOOL_FAILURE_BURST",
    }
