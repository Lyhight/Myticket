from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, require_supervisor
from app.db.session import get_db
from app.models.user import User
from app.schemas.feedback import (
    FeedbackCreate,
    FeedbackResponse,
    KnowledgeGapApprove,
    KnowledgeGapReject,
    KnowledgeGapResponse,
)
from app.services.feedback_service import FeedbackService


router = APIRouter(prefix="/feedback", tags=["Feedback Flywheel"])


@router.get("", response_model=list[FeedbackResponse])
async def list_ticket_feedback(
    ticket_id: int = Query(gt=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await FeedbackService(db).list_for_ticket(current_user, ticket_id)


@router.post("", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
async def submit_feedback(
    data: FeedbackCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await FeedbackService(db).submit(current_user, data)


@router.get("/gaps", response_model=list[KnowledgeGapResponse])
async def list_knowledge_gaps(
    gap_status: str | None = Query(default="PENDING", alias="status"),
    supervisor: User = Depends(require_supervisor),
    db: AsyncSession = Depends(get_db),
):
    return await FeedbackService(db).list_gaps(gap_status)


@router.post("/gaps/{gap_id}/approve", response_model=KnowledgeGapResponse)
async def approve_knowledge_gap(
    gap_id: int,
    data: KnowledgeGapApprove,
    supervisor: User = Depends(require_supervisor),
    db: AsyncSession = Depends(get_db),
):
    return await FeedbackService(db).approve_gap(gap_id, supervisor, data)


@router.post("/gaps/{gap_id}/reject", response_model=KnowledgeGapResponse)
async def reject_knowledge_gap(
    gap_id: int,
    data: KnowledgeGapReject,
    supervisor: User = Depends(require_supervisor),
    db: AsyncSession = Depends(get_db),
):
    return await FeedbackService(db).reject_gap(
        gap_id, supervisor, data.reviewer_note
    )
