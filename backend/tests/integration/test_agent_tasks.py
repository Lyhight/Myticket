from app.models.ticket import Ticket
from app.models.user import User
from app.repositories.agent_task_repository import AgentTaskRepository
from app.repositories.message_repository import MessageRepository
from datetime import datetime, timedelta, timezone


async def test_task_lifecycle_and_message_idempotency(db_session) -> None:
    user = User(email="task@example.com", password_hash="hash")
    db_session.add(user)
    await db_session.flush()
    ticket = Ticket(user_id=user.id, title="任务测试")
    db_session.add(ticket)
    await db_session.commit()
    await db_session.refresh(ticket)

    tasks = AgentTaskRepository(db_session)
    first = await tasks.create_or_get(
        key="user:1:request-1",
        ticket_id=ticket.id,
        user_id=user.id,
        content="查询订单",
    )
    duplicate = await tasks.create_or_get(
        key="user:1:request-1",
        ticket_id=ticket.id,
        user_id=user.id,
        content="查询订单",
    )
    assert duplicate.id == first.id

    await tasks.mark_running(first)
    assert first.status == "RUNNING"
    assert first.attempts == 1
    await tasks.mark_failed(first, "temporary failure")
    assert first.status == "FAILED"
    assert first.next_retry_at is not None

    messages = MessageRepository(db_session)
    one = await messages.create(
        ticket_id=ticket.id,
        sender_type="CUSTOMER",
        content="查询订单",
        operation_key=f"agent-task:{first.id}:customer",
    )
    two = await messages.create(
        ticket_id=ticket.id,
        sender_type="CUSTOMER",
        content="查询订单",
        operation_key=f"agent-task:{first.id}:customer",
    )
    assert one.id == two.id

    await tasks.mark_running(first)
    await tasks.mark_succeeded(first, one.id)
    assert first.status == "SUCCEEDED"
    assert first.attempts == 2


async def test_worker_claim_and_expired_lease_recovery(db_session) -> None:
    user = User(email="worker@example.com", password_hash="hash")
    db_session.add(user)
    await db_session.flush()
    ticket = Ticket(user_id=user.id, title="Worker测试")
    db_session.add(ticket)
    await db_session.commit()
    await db_session.refresh(ticket)
    repository = AgentTaskRepository(db_session)
    task = await repository.create_or_get(
        key="user:worker:request-1",
        ticket_id=ticket.id,
        user_id=user.id,
        content="异步查询",
    )

    claimed = await repository.claim_next(
        worker_id="worker-a", lease_seconds=60
    )
    assert claimed is not None
    assert claimed.id == task.id
    assert claimed.status == "RUNNING"
    assert claimed.locked_by == "worker-a"
    assert claimed.attempts == 1
    assert await repository.claim_next(worker_id="worker-b") is None

    claimed.lease_expires_at = (
        datetime.now(timezone.utc).replace(tzinfo=None)
        - timedelta(seconds=1)
    )
    await db_session.commit()
    recovered = await repository.claim_next(worker_id="worker-b")
    assert recovered is not None
    assert recovered.id == task.id
    assert recovered.locked_by == "worker-b"
    assert recovered.attempts == 2
    stale_heartbeat = await repository.heartbeat_by_id(
        task.id,
        worker_id="worker-a",
        attempt=1,
    )
    assert stale_heartbeat is False
    current_heartbeat = await repository.heartbeat_by_id(
        task.id,
        worker_id="worker-b",
        attempt=2,
    )
    assert current_heartbeat is True
    stale_completion = await repository.complete_claimed(
        task_id=task.id,
        worker_id="worker-a",
        attempt=1,
        message_id=None,
    )
    assert stale_completion is False
    await db_session.refresh(recovered)
    assert recovered.status == "RUNNING"
    assert recovered.locked_by == "worker-b"


async def test_expired_final_attempt_is_reaped_as_dead(db_session) -> None:
    user = User(email="exhausted@example.com", password_hash="hash")
    db_session.add(user)
    await db_session.flush()
    ticket = Ticket(user_id=user.id, title="耗尽任务")
    db_session.add(ticket)
    await db_session.commit()
    await db_session.refresh(ticket)
    repository = AgentTaskRepository(db_session)
    task = await repository.create_or_get(
        key="user:exhausted:request-1",
        ticket_id=ticket.id,
        user_id=user.id,
        content="最终尝试",
    )
    task.max_attempts = 1
    await db_session.commit()

    claimed = await repository.claim_next(
        worker_id="worker-final",
        lease_seconds=60,
    )
    assert claimed is not None
    claimed.lease_expires_at = (
        datetime.now(timezone.utc).replace(tzinfo=None)
        - timedelta(seconds=1)
    )
    await db_session.commit()

    assert await repository.claim_next(worker_id="worker-next") is None
    await db_session.refresh(claimed)
    assert claimed.status == "DEAD"
    assert claimed.locked_by is None
    assert claimed.lease_expires_at is None
    assert "retry budget" in claimed.last_error
