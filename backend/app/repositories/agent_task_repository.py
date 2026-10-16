from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.models.agent_task import AgentTask
from app.core.config import settings


class AgentTaskRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, task_id: int) -> AgentTask | None:
        return await self.db.get(AgentTask, task_id)

    async def get_by_key(self, key: str) -> AgentTask | None:
        result = await self.db.execute(select(AgentTask).where(AgentTask.idempotency_key == key))
        return result.scalar_one_or_none()

    async def create_or_get(self, *, key: str, ticket_id: int, user_id: int, content: str) -> AgentTask:
        existing = await self.get_by_key(key)
        if existing:
            return existing
        task = AgentTask(
            idempotency_key=key,
            ticket_id=ticket_id,
            user_id=user_id,
            task_type="ticket_message",
            payload={"content": content},
            max_attempts=settings.agent_task_max_attempts,
        )
        self.db.add(task)
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            existing = await self.get_by_key(key)
            if existing is not None:
                return existing
            raise
        await self.db.refresh(task)
        return task

    async def allow_manual_retry(self, task: AgentTask) -> None:
        task.next_retry_at = None
        await self.db.commit()

    async def mark_running(self, task: AgentTask) -> None:
        task.status = "RUNNING"
        task.attempts += 1
        task.last_error = None
        task.next_retry_at = None
        task.locked_by = None
        task.lease_expires_at = None
        await self.db.commit()

    async def mark_succeeded(self, task: AgentTask, message_id: int | None) -> None:
        task.status = "SUCCEEDED"
        task.result_message_id = message_id
        task.next_retry_at = None
        task.locked_by = None
        task.lease_expires_at = None
        await self.db.commit()

    async def mark_failed(self, task: AgentTask, error: str) -> None:
        task.status = "DEAD" if task.attempts >= task.max_attempts else "FAILED"
        task.last_error = error[:2000]
        task.next_retry_at = (
            None if task.status == "DEAD" else
            datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=min(300, 2 ** task.attempts))
        )
        task.locked_by = None
        task.lease_expires_at = None
        await self.db.commit()

    async def claim_next(
        self,
        *,
        worker_id: str,
        lease_seconds: int = 60,
    ) -> AgentTask | None:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        # An expired final attempt cannot be claimed again, but must not stay
        # RUNNING forever after a worker crash.
        await self.db.execute(
            update(AgentTask)
            .where(
                AgentTask.status == "RUNNING",
                AgentTask.lease_expires_at.is_not(None),
                AgentTask.lease_expires_at <= now,
                AgentTask.attempts >= AgentTask.max_attempts,
            )
            .values(
                status="DEAD",
                last_error="Worker lease expired after retry budget was exhausted",
                locked_by=None,
                lease_expires_at=None,
                next_retry_at=None,
            )
        )
        await self.db.commit()
        eligible = or_(
            AgentTask.status == "PENDING",
            and_(
                AgentTask.status == "FAILED",
                or_(
                    AgentTask.next_retry_at.is_(None),
                    AgentTask.next_retry_at <= now,
                ),
            ),
            and_(
                AgentTask.status == "RUNNING",
                AgentTask.lease_expires_at.is_not(None),
                AgentTask.lease_expires_at <= now,
            ),
        )
        result = await self.db.execute(
            select(AgentTask)
            .where(eligible, AgentTask.attempts < AgentTask.max_attempts)
            .order_by(AgentTask.created_at.asc(), AgentTask.id.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        task = result.scalar_one_or_none()
        if task is None:
            await self.db.rollback()
            return None
        task.status = "RUNNING"
        task.attempts += 1
        task.locked_by = worker_id
        task.heartbeat_at = now
        task.lease_expires_at = now + timedelta(seconds=lease_seconds)
        task.next_retry_at = None
        task.last_error = None
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def heartbeat(
        self,
        task: AgentTask,
        *,
        worker_id: str,
        lease_seconds: int = 60,
    ) -> bool:
        if task.status != "RUNNING" or task.locked_by != worker_id:
            return False
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        task.heartbeat_at = now
        task.lease_expires_at = now + timedelta(seconds=lease_seconds)
        await self.db.commit()
        return True

    async def heartbeat_by_id(
        self,
        task_id: int,
        *,
        worker_id: str,
        attempt: int,
        lease_seconds: int = 60,
    ) -> bool:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        result = await self.db.execute(
            update(AgentTask)
            .where(
                AgentTask.id == task_id,
                AgentTask.status == "RUNNING",
                AgentTask.locked_by == worker_id,
                AgentTask.attempts == attempt,
            )
            .values(
                heartbeat_at=now,
                lease_expires_at=now + timedelta(seconds=lease_seconds),
            )
        )
        await self.db.commit()
        return result.rowcount == 1

    async def complete_claimed(
        self,
        *,
        task_id: int,
        worker_id: str,
        attempt: int,
        message_id: int | None,
    ) -> bool:
        result = await self.db.execute(
            update(AgentTask)
            .where(
                AgentTask.id == task_id,
                AgentTask.status == "RUNNING",
                AgentTask.locked_by == worker_id,
                AgentTask.attempts == attempt,
            )
            .values(
                status="SUCCEEDED",
                result_message_id=message_id,
                locked_by=None,
                lease_expires_at=None,
                next_retry_at=None,
            )
        )
        await self.db.commit()
        return result.rowcount == 1

    async def fail_claimed(
        self,
        *,
        task_id: int,
        worker_id: str,
        attempt: int,
        max_attempts: int,
        error: str,
    ) -> bool:
        terminal = attempt >= max_attempts
        result = await self.db.execute(
            update(AgentTask)
            .where(
                AgentTask.id == task_id,
                AgentTask.status == "RUNNING",
                AgentTask.locked_by == worker_id,
                AgentTask.attempts == attempt,
            )
            .values(
                status="DEAD" if terminal else "FAILED",
                last_error=error[:2000],
                next_retry_at=(
                    None if terminal else
                    datetime.now(timezone.utc).replace(tzinfo=None)
                    + timedelta(seconds=min(300, 2 ** attempt))
                ),
                locked_by=None,
                lease_expires_at=None,
            )
        )
        await self.db.commit()
        return result.rowcount == 1

    async def list_failed(self, *, limit: int = 100) -> list[AgentTask]:
        result = await self.db.execute(
            select(AgentTask).where(AgentTask.status.in_(("FAILED", "DEAD"))).order_by(AgentTask.updated_at.desc()).limit(limit)
        )
        return list(result.scalars().all())
