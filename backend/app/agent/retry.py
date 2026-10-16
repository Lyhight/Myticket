"""通用：带超时 + 指数退避重试地执行异步任务。

供决策 / 回复等 LLM 调用复用，
与分类器 AgentRuntime 采用一致的重试策略。
"""
import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


async def run_with_retry(
    coro_factory: Callable[[], Awaitable[T]],
    *,
    timeout_seconds: float,
    max_retries: int,
    retry_delay_seconds: float,
) -> T:
    """
    执行 coro_factory()，超时或异常则指数退避重试。

    coro_factory 每次调用必须返回一个全新的协程，
    避免同一个协程被 await 多次。

    重试耗尽后抛出最后一次异常，
    由调用方决定兜底策略。
    """

    total_attempts = max_retries + 1
    last_error: Exception | None = None

    for attempt in range(1, total_attempts + 1):

        try:
            return await asyncio.wait_for(
                coro_factory(),
                timeout=timeout_seconds,
            )

        except asyncio.TimeoutError as exc:
            last_error = exc

            logger.warning(
                "Attempt %s/%s timed out",
                attempt,
                total_attempts,
            )

        except Exception as exc:
            last_error = exc

            logger.warning(
                "Attempt %s/%s failed: %s",
                attempt,
                total_attempts,
                exc,
            )

        if attempt < total_attempts:

            delay = (
                retry_delay_seconds
                * (2 ** (attempt - 1))
            )

            logger.info(
                "Retrying in %.1f seconds",
                delay,
            )

            await asyncio.sleep(delay)

    assert last_error is not None
    raise last_error
