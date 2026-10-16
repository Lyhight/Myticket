from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_admin
from app.db.session import get_db
from app.models.user import User
from app.operations.metrics import AgentOperationsService
from app.schemas.agent_task import AgentTaskResponse
from app.services.ticket_service import TicketService


router = APIRouter(prefix="/operations", tags=["Operations"])


@router.get("/metrics")
async def agent_metrics(
    hours: int = Query(default=24, ge=1, le=168),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await AgentOperationsService(db).snapshot(hours=hours)


@router.get("/alerts")
async def agent_alerts(
    hours: int = Query(default=24, ge=1, le=168),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    service = AgentOperationsService(db)
    metrics = await service.snapshot(hours=hours)
    return {"metrics": metrics, "alerts": service.alerts(metrics)}


@router.get("/tasks/failed", response_model=list[AgentTaskResponse])
async def failed_agent_tasks(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await TicketService(db).list_failed_tasks()


@router.post("/tasks/{task_id}/retry")
async def retry_agent_task(
    task_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    message = await TicketService(db).retry_task(task_id)
    return {
        "status": "SUCCEEDED",
        "message_id": message.id if message else None,
    }
