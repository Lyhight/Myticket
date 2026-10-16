import asyncio
from types import SimpleNamespace

from app.workers import agent_worker
from app.workers.agent_worker import AgentWorker


class FakeSessionContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class ClaimingRepository:
    def __init__(self, _db) -> None:
        pass

    async def claim_next(self, **_kwargs):
        return SimpleNamespace(
            id=42,
            attempts=2,
            task_type="ticket_message",
        )


async def test_worker_cancels_execution_after_lease_loss(
    monkeypatch,
) -> None:
    started = asyncio.Event()
    cancelled = asyncio.Event()
    worker = AgentWorker(
        worker_id="worker-test",
        poll_seconds=0.1,
        lease_seconds=10,
    )

    async def fake_execute(_task_id: int, _attempt: int) -> None:
        started.set()
        try:
            await asyncio.sleep(60)
        finally:
            cancelled.set()

    async def fake_heartbeat(
        _task_id: int,
        _attempt: int,
        _stop: asyncio.Event,
        lease_lost: asyncio.Event,
    ) -> None:
        await started.wait()
        lease_lost.set()

    monkeypatch.setattr(
        agent_worker,
        "AsyncSessionLocal",
        lambda: FakeSessionContext(),
    )
    monkeypatch.setattr(
        agent_worker,
        "AgentTaskRepository",
        ClaimingRepository,
    )
    monkeypatch.setattr(worker, "_execute_task", fake_execute)
    monkeypatch.setattr(worker, "_heartbeat_loop", fake_heartbeat)

    assert await worker.run_once() is True
    assert cancelled.is_set()
