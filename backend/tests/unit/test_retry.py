import asyncio

import pytest

from app.agent.retry import run_with_retry


async def test_success_returns_immediately() -> None:
    calls = 0

    async def operation() -> str:
        nonlocal calls
        calls += 1
        return "success"

    result = await run_with_retry(
        operation,
        timeout_seconds=1,
        max_retries=2,
        retry_delay_seconds=0,
    )

    assert result == "success"
    assert calls == 1


async def test_failure_then_success_retries() -> None:
    calls = 0

    async def operation() -> str:
        nonlocal calls
        calls += 1

        if calls < 2:
            raise RuntimeError(
                "temporary failure"
            )

        return "recovered"

    result = await run_with_retry(
        operation,
        timeout_seconds=1,
        max_retries=2,
        retry_delay_seconds=0,
    )

    assert result == "recovered"
    assert calls == 2


async def test_exhausted_retries_raise_last_error() -> None:
    calls = 0

    async def operation() -> str:
        nonlocal calls
        calls += 1
        raise RuntimeError(
            f"failure attempt {calls}"
        )

    with pytest.raises(
        RuntimeError,
        match="failure attempt 3",
    ):
        await run_with_retry(
            operation,
            timeout_seconds=1,
            max_retries=2,
            retry_delay_seconds=0,
        )

    assert calls == 3


async def test_timeout_is_raised_after_retries() -> None:
    calls = 0

    async def slow_operation() -> str:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.05)
        return "too late"

    with pytest.raises(asyncio.TimeoutError):
        await run_with_retry(
            slow_operation,
            timeout_seconds=0.005,
            max_retries=1,
            retry_delay_seconds=0,
        )

    assert calls == 2