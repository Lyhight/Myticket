import asyncio
import logging
import socket
from contextlib import suppress
from time import perf_counter
from uuid import uuid4

from app.db.session import AsyncSessionLocal
from app.core.config import settings
from app.repositories.agent_task_repository import AgentTaskRepository
from app.services.ticket_service import TicketService
from app.core.logging import reset_correlation_id, set_correlation_id
from app.operations.observability import WORKER_TASK_DURATION, WORKER_TASKS


logger = logging.getLogger(__name__)


class TaskLeaseLostError(RuntimeError):
    pass


class AgentWorker:
    def __init__(
        self,
        *,
        worker_id: str | None = None,
        poll_seconds: float | None = None,
        lease_seconds: int | None = None,
    ) -> None:
        self.worker_id = worker_id or (
            f"{socket.gethostname()}-{uuid4().hex[:8]}"
        )
        self.poll_seconds = (
            settings.agent_worker_poll_seconds
            if poll_seconds is None else poll_seconds
        )
        self.lease_seconds = (
            settings.agent_task_lease_seconds
            if lease_seconds is None else lease_seconds
        )

    async def run_once(self) -> bool:
        async with AsyncSessionLocal() as db:
            task = await AgentTaskRepository(db).claim_next(
                worker_id=self.worker_id,
                lease_seconds=self.lease_seconds,
            )
        if task is None:
            return False

        task_started = perf_counter()
        outcome = "cancelled"
        stop_heartbeat = asyncio.Event()
        lease_lost = asyncio.Event()
        heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(
                task.id,
                task.attempts,
                stop_heartbeat,
                lease_lost,
            )
        )
        execution_task = asyncio.create_task(
            self._execute_task(task.id, task.attempts)
        )
        lease_watch_task = asyncio.create_task(lease_lost.wait())
        try:
            done, _ = await asyncio.wait(
                {execution_task, lease_watch_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if execution_task in done:
                await execution_task
                outcome = "succeeded"
            else:
                execution_task.cancel()
                with suppress(asyncio.CancelledError):
                    await execution_task
                raise TaskLeaseLostError(
                    f"Task {task.id} attempt {task.attempts} lease was lost"
                )
        except TaskLeaseLostError:
            outcome = "lease_lost"
            logger.warning(
                "agent_task_stale_execution_cancelled task_id=%s attempt=%s",
                task.id,
                task.attempts,
            )
        except Exception as exc:
            outcome = "failed"
            logger.exception("agent_task_failed task_id=%s", task.id)
            async with AsyncSessionLocal() as db:
                repository = AgentTaskRepository(db)
                current = await repository.get_by_id(task.id)
                if current and current.status == "RUNNING":
                    await repository.fail_claimed(
                        task_id=current.id,
                        worker_id=self.worker_id,
                        attempt=task.attempts,
                        max_attempts=current.max_attempts,
                        error=str(exc),
                    )
        finally:
            stop_heartbeat.set()
            lease_watch_task.cancel()
            with suppress(asyncio.CancelledError):
                await lease_watch_task
            await heartbeat_task
            WORKER_TASKS.labels(
                task_type=task.task_type,
                outcome=outcome,
            ).inc()
            WORKER_TASK_DURATION.labels(
                task_type=task.task_type,
            ).observe(perf_counter() - task_started)
        return True

    async def _execute_task(self, task_id: int, attempt: int) -> None:
        correlation_token = set_correlation_id(
            f"task-{task_id}-attempt-{attempt}"
        )
        try:
            async with AsyncSessionLocal() as db:
                await TicketService(db).execute_claimed_task(
                    task_id=task_id,
                    worker_id=self.worker_id,
                    attempt=attempt,
                )
        finally:
            reset_correlation_id(correlation_token)

    async def run_forever(self) -> None:
        logger.info("agent_worker_started worker_id=%s", self.worker_id)
        while True:
            try:
                processed = await self.run_once()
            except Exception:
                logger.exception(
                    "agent_worker_iteration_failed worker_id=%s",
                    self.worker_id,
                )
                await asyncio.sleep(self.poll_seconds)
                continue
            if not processed:
                await asyncio.sleep(self.poll_seconds)

    async def _heartbeat_loop(
        self,
        task_id: int,
        attempt: int,
        stop: asyncio.Event,
        lease_lost: asyncio.Event,
    ) -> None:
        interval = max(1.0, self.lease_seconds / 3)
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
                break
            except asyncio.TimeoutError:
                try:
                    async with AsyncSessionLocal() as db:
                        alive = await AgentTaskRepository(db).heartbeat_by_id(
                            task_id,
                            worker_id=self.worker_id,
                            attempt=attempt,
                            lease_seconds=self.lease_seconds,
                        )
                except Exception:
                    logger.exception(
                        "agent_task_heartbeat_failed task_id=%s attempt=%s",
                        task_id,
                        attempt,
                    )
                    continue
                if not alive:
                    logger.warning(
                        "agent_task_lease_lost task_id=%s attempt=%s",
                        task_id,
                        attempt,
                    )
                    lease_lost.set()
                    break
