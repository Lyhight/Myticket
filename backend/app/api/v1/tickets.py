import asyncio
import json
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    get_current_user,
    require_support_agent,
    require_supervisor,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.ticket import (
    TicketCreate,
    TicketDetailResponse,
    HandoffQueueResponse,
    TicketRejectRequest,
    TicketResponse,
)
from app.services.ticket_service import TicketService
from app.schemas.agent_run import AgentRunResponse
from app.schemas.message import (
    MessageCreate,
    MessageResponse,
)
from app.core.config import settings
from app.operations.rate_limit import create_rate_limiter
from app.schemas.agent_task import AgentTaskAccepted, AgentTaskStatusResponse


logger = logging.getLogger(__name__)

agent_rate_limiter = create_rate_limiter(
    limit=settings.agent_rate_limit_per_minute,
    window_seconds=60,
    detail="Agent request rate limit exceeded",
)


async def enforce_agent_rate_limit(
    current_user: User = Depends(get_current_user),
) -> None:
    await agent_rate_limiter.consume(f"user:{current_user.id}")
router = APIRouter(
    prefix="/tickets",
    tags=["Tickets"],
)


@router.post(
    "",
    response_model=TicketResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(enforce_agent_rate_limit)],
)
async def create_ticket(
    data: TicketCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = TicketService(db)

    return await service.create_ticket(
        current_user,
        data,
    )


@router.get(
    "",
    response_model=list[TicketResponse],
)
async def list_tickets(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = TicketService(db)

    return await service.list_tickets(
        current_user
    )


@router.get(
    "/pending",
    response_model=list[TicketResponse],
)
async def list_pending_tickets(
    supervisor: User = Depends(require_supervisor),
    db: AsyncSession = Depends(get_db),
):
    service = TicketService(db)

    return await service.list_pending_tickets()


@router.get("/handoff", response_model=HandoffQueueResponse)
async def list_handoff_tickets(
    agent: User = Depends(require_support_agent),
    db: AsyncSession = Depends(get_db),
):
    service = TicketService(db)
    return {
        "waiting": await service.list_handoff_queue(),
        "assigned": await service.list_assigned_tickets(agent),
    }


@router.post("/{ticket_id}/claim", response_model=TicketResponse)
async def claim_handoff_ticket(
    ticket_id: int,
    agent: User = Depends(require_support_agent),
    db: AsyncSession = Depends(get_db),
):
    return await TicketService(db).claim_handoff(agent, ticket_id)


@router.post("/{ticket_id}/human-messages", response_model=MessageResponse)
async def send_human_support_message(
    ticket_id: int,
    data: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await TicketService(db).send_human_message(
        current_user, ticket_id, data.content
    )


@router.post("/{ticket_id}/resolve", response_model=TicketResponse)
async def resolve_handoff_ticket(
    ticket_id: int,
    agent: User = Depends(require_support_agent),
    db: AsyncSession = Depends(get_db),
):
    return await TicketService(db).resolve_handoff(agent, ticket_id)


@router.get(
    "/{ticket_id}",
    response_model=TicketDetailResponse,
)
async def get_ticket(
    ticket_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = TicketService(db)

    return await service.get_ticket(
        current_user,
        ticket_id,
    )


@router.delete(
    "/{ticket_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_ticket(
    ticket_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = TicketService(db)
    await service.delete_ticket(current_user, ticket_id)


@router.get(
    "/{ticket_id}/agent-runs",
    response_model=list[AgentRunResponse],
)
async def list_agent_runs(
    ticket_id: int,
    current_user: User = Depends(
        get_current_user
    ),
    db: AsyncSession = Depends(get_db),
):
    service = TicketService(db)

    return await service.list_agent_runs(
        current_user=current_user,
        ticket_id=ticket_id,
    )


@router.post(
    "/{ticket_id}/messages/stream",
    dependencies=[Depends(enforce_agent_rate_limit)],
)
async def stream_ticket_message(
    ticket_id: int,
    data: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        min_length=8,
        max_length=128,
    ),
):
    service = TicketService(db)
    await service.get_ticket(current_user, ticket_id)

    def event(event_type: str, **payload) -> str:
        return json.dumps(
            {"type": event_type, **payload},
            ensure_ascii=False,
        ) + "\n"

    async def generate():
        stages = [
            ("understanding", "正在理解问题与历史对话"),
            ("retrieving", "正在检索知识库与长期记忆"),
            ("acting", "正在规划并执行所需工具"),
        ]
        for step, label in stages:
            yield event("status", step=step, label=label)
            await asyncio.sleep(0.12)

        try:
            message = await service.send_message(
                current_user=current_user,
                ticket_id=ticket_id,
                content=data.content,
                idempotency_key=idempotency_key,
            )
        except HTTPException as exc:
            yield event("error", message=str(exc.detail))
            return
        except Exception:
            logger.exception(
                "Streaming ticket message failed ticket_id=%s",
                ticket_id,
            )
            yield event("error", message="处理失败，请稍后重试")
            return

        if message is None:
            yield event(
                "status",
                step="human_review",
                label="该请求已转入人工审批",
            )
        else:
            yield event("status", step="responding", label="正在生成回复")
            content = message.content
            for index in range(0, len(content), 3):
                yield event("delta", content=content[index:index + 3])
                await asyncio.sleep(0.018)

        yield event("done")

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/{ticket_id}/messages",
    response_model=MessageResponse | None,
    dependencies=[Depends(enforce_agent_rate_limit)],
)
async def send_ticket_message(
    ticket_id: int,
    data: MessageCreate,
    current_user: User = Depends(
        get_current_user
    ),
    db: AsyncSession = Depends(
        get_db
    ),
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        min_length=8,
        max_length=128,
    ),
):
    service = TicketService(
        db
    )

    return await service.send_message(
        current_user=current_user,
        ticket_id=ticket_id,
        content=data.content,
        idempotency_key=idempotency_key,
    )


@router.post(
    "/{ticket_id}/messages/async",
    response_model=AgentTaskAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(enforce_agent_rate_limit)],
)
async def enqueue_ticket_message(
    ticket_id: int,
    data: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        min_length=8,
        max_length=128,
    ),
):
    task = await TicketService(db).enqueue_message(
        current_user=current_user,
        ticket_id=ticket_id,
        content=data.content,
        idempotency_key=idempotency_key,
    )
    return AgentTaskAccepted(
        task_id=task.id,
        status=task.status,
        idempotency_key=task.idempotency_key.split(":", 2)[-1],
    )


@router.get(
    "/{ticket_id}/tasks/{task_id}",
    response_model=AgentTaskStatusResponse,
)
async def get_agent_task(
    ticket_id: int,
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await TicketService(db).get_task(
        current_user=current_user,
        ticket_id=ticket_id,
        task_id=task_id,
    )

@router.post(
    "/{ticket_id}/approve",
    response_model=TicketResponse,
)
async def approve_ticket(
    ticket_id: int,
    supervisor: User = Depends(require_supervisor),
    db: AsyncSession = Depends(get_db),
):
    service = TicketService(db)

    return await service.approve_ticket(ticket_id)


@router.post(
    "/{ticket_id}/reject",
    response_model=TicketResponse,
)
async def reject_ticket(
    ticket_id: int,
    data: TicketRejectRequest,
    supervisor: User = Depends(require_supervisor),
    db: AsyncSession = Depends(get_db),
):
    service = TicketService(db)

    return await service.reject_ticket(
        ticket_id,
        data.content,
    )
