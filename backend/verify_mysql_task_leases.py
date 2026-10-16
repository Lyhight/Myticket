"""Exercise MySQL SKIP LOCKED claims and attempt fencing in CI."""

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import delete, update

from app.db.session import AsyncSessionLocal
from app.models.agent_task import AgentTask
from app.models.ticket import Ticket
from app.models.user import User
from app.repositories.agent_task_repository import AgentTaskRepository


async def claim(worker_id: str):
    async with AsyncSessionLocal() as db:
        return await AgentTaskRepository(db).claim_next(
            worker_id=worker_id,
            lease_seconds=60,
        )


async def main() -> None:
    suffix = uuid4().hex
    async with AsyncSessionLocal() as db:
        user = User(
            email=f"lease-smoke-{suffix}@example.com",
            password_hash="not-used",
        )
        db.add(user)
        await db.flush()
        ticket = Ticket(user_id=user.id, title="MySQL lease smoke")
        db.add(ticket)
        await db.commit()
        task = await AgentTaskRepository(db).create_or_get(
            key=f"lease-smoke:{suffix}",
            ticket_id=ticket.id,
            user_id=user.id,
            content="verify concurrent claim",
        )
        task_id, ticket_id, user_id = task.id, ticket.id, user.id

    try:
        results = await asyncio.gather(claim("mysql-worker-a"), claim("mysql-worker-b"))
        winners = [item for item in results if item is not None]
        if len(winners) != 1:
            raise RuntimeError(f"Expected one task claimant, got {len(winners)}")
        first = winners[0]

        async with AsyncSessionLocal() as db:
            repo = AgentTaskRepository(db)
            stale_heartbeat = await repo.heartbeat_by_id(
                task_id,
                worker_id=first.locked_by,
                attempt=first.attempts + 1,
            )
            if stale_heartbeat:
                raise RuntimeError("Invalid fencing token renewed the lease")
            await db.execute(
                update(AgentTask)
                .where(AgentTask.id == task_id)
                .values(
                    lease_expires_at=(
                        datetime.now(timezone.utc).replace(tzinfo=None)
                        - timedelta(seconds=1)
                    )
                )
            )
            await db.commit()

        recovered = await claim("mysql-worker-recovery")
        if recovered is None or recovered.attempts != first.attempts + 1:
            raise RuntimeError("Expired task was not recovered with a new attempt")

        async with AsyncSessionLocal() as db:
            stale_completion = await AgentTaskRepository(db).complete_claimed(
                task_id=task_id,
                worker_id=first.locked_by,
                attempt=first.attempts,
                message_id=None,
            )
            if stale_completion:
                raise RuntimeError("Stale worker completed a recovered task")
        print("mysql task lease smoke: ok")
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(AgentTask).where(AgentTask.id == task_id))
            await db.execute(delete(Ticket).where(Ticket.id == ticket_id))
            await db.execute(delete(User).where(User.id == user_id))
            await db.commit()


if __name__ == "__main__":
    asyncio.run(main())
