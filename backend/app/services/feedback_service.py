import hashlib
import re

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.schemas import CustomerServiceAgentResult
from app.agent.state import AgentState
from app.models.agent_run import AgentRun
from app.models.domain_event import DomainEvent
from app.models.feedback import KnowledgeGap
from app.models.message import Message
from app.models.user import User
from app.operations.observability import (
    observe_knowledge_gap,
    observe_message_feedback,
)
from app.repositories.agent_run_repository import AgentRunRepository
from app.repositories.feedback_repository import FeedbackRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.ticket_repository import TicketRepository
from app.schemas.feedback import FeedbackCreate, KnowledgeGapApprove
from app.schemas.knowledge import KnowledgeDocumentCreate
from app.services.knowledge_service import KnowledgeAdminService


class FeedbackService:
    """Close the loop from bad answers to reviewed, searchable knowledge."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.feedback_repo = FeedbackRepository(db)
        self.ticket_repo = TicketRepository(db)
        self.message_repo = MessageRepository(db)
        self.agent_run_repo = AgentRunRepository(db)

    async def submit(self, current_user: User, data: FeedbackCreate):
        ticket = await self.ticket_repo.get_by_id(data.ticket_id)
        if ticket is None:
            raise HTTPException(status_code=404, detail="Ticket not found")
        if ticket.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Feedback is limited to the ticket owner")
        message = await self.message_repo.get_by_id(data.message_id)
        if message is None or message.ticket_id != ticket.id:
            raise HTTPException(status_code=404, detail="Message not found")
        if message.sender_type != "AI":
            raise HTTPException(
                status_code=400,
                detail="Only Agent messages can receive model feedback",
            )

        previous_feedback = await self.feedback_repo.get_message_feedback(
            message.id, current_user.id
        )
        is_new_negative_signal = (
            data.rating == "DOWN"
            and (
                previous_feedback is None
                or previous_feedback.rating != "DOWN"
            )
        )
        run = await self.agent_run_repo.get_latest_by_ticket(ticket.id)
        feedback = await self.feedback_repo.save_feedback(
            ticket_id=ticket.id,
            message_id=message.id,
            agent_run_id=run.id if run else None,
            user_id=current_user.id,
            rating=data.rating,
            comment=data.comment,
        )
        if is_new_negative_signal:
            question = await self._question_before(message)
            gap = await self.feedback_repo.upsert_gap(
                fingerprint=self._fingerprint(question),
                ticket_id=ticket.id,
                agent_run_id=run.id if run else None,
                feedback_id=feedback.id,
                question=question,
                suggested_answer=message.content,
                source="user_feedback",
                reason="negative_feedback",
            )
            self.db.add(
                DomainEvent(
                    event_type="knowledge_gap.created",
                    aggregate_type="knowledge_gap",
                    aggregate_id=gap.id,
                    audience_role="supervisor",
                    payload={
                        "gap_id": gap.id,
                        "ticket_id": ticket.id,
                        "reason": gap.reason,
                    },
                )
            )
        await self.db.commit()
        await self.db.refresh(feedback)
        observe_message_feedback(data.rating)
        if is_new_negative_signal:
            observe_knowledge_gap("detected", "negative_feedback")
        return feedback

    async def list_for_ticket(self, current_user: User, ticket_id: int):
        ticket = await self.ticket_repo.get_by_id(ticket_id)
        if ticket is None:
            raise HTTPException(status_code=404, detail="Ticket not found")
        if ticket.user_id != current_user.id:
            raise HTTPException(
                status_code=403,
                detail="Feedback is limited to the ticket owner",
            )
        return await self.feedback_repo.list_ticket_feedback(
            ticket_id, current_user.id
        )

    async def capture_agent_failure(
        self,
        *,
        ticket_id: int,
        run: AgentRun,
        question: str,
        result: CustomerServiceAgentResult,
        state: AgentState,
        retrieved_knowledge: list[dict],
    ) -> KnowledgeGap | None:
        reason = self._automatic_reason(result, state, retrieved_knowledge)
        if reason is None:
            return None
        gap = await self.feedback_repo.upsert_gap(
            fingerprint=self._fingerprint(question),
            ticket_id=ticket_id,
            agent_run_id=run.id,
            feedback_id=None,
            question=question,
            suggested_answer=result.reply,
            source="agent_runtime",
            reason=reason,
        )
        self.db.add(
            DomainEvent(
                event_type="knowledge_gap.created",
                aggregate_type="knowledge_gap",
                aggregate_id=gap.id,
                audience_role="supervisor",
                payload={"gap_id": gap.id, "ticket_id": ticket_id, "reason": reason},
            )
        )
        await self.db.commit()
        observe_knowledge_gap("detected", reason)
        return gap

    async def list_gaps(self, gap_status: str | None):
        if gap_status and gap_status not in {"PENDING", "APPROVED", "REJECTED"}:
            raise HTTPException(status_code=400, detail="Invalid knowledge gap status")
        return await self.feedback_repo.list_gaps(gap_status)

    async def approve_gap(
        self,
        gap_id: int,
        reviewer: User,
        data: KnowledgeGapApprove,
    ) -> KnowledgeGap:
        gap = await self._pending_gap(gap_id)
        title = data.title or f"知识缺口：{gap.question[:80]}"
        source = f"flywheel://knowledge-gap/{gap.id}"
        document, _ = await KnowledgeAdminService(self.db).create_document(
            KnowledgeDocumentCreate(
                title=title,
                source=source,
                content=f"问题：{gap.question}\n答案：{data.approved_answer}",
            )
        )
        gap.suggested_answer = data.approved_answer
        reviewed = await self.feedback_repo.mark_reviewed(
            gap,
            status="APPROVED",
            reviewer_id=reviewer.id,
            reviewer_note=data.reviewer_note,
            knowledge_document_id=document.id,
        )
        self.db.add(
            DomainEvent(
                event_type="knowledge_gap.approved",
                aggregate_type="knowledge_gap",
                aggregate_id=gap.id,
                audience_role="admin",
                payload={"gap_id": gap.id, "knowledge_document_id": document.id},
            )
        )
        await self.db.commit()
        observe_knowledge_gap("approved", gap.reason)
        return reviewed

    async def reject_gap(
        self,
        gap_id: int,
        reviewer: User,
        reviewer_note: str,
    ) -> KnowledgeGap:
        gap = await self._pending_gap(gap_id)
        reviewed = await self.feedback_repo.mark_reviewed(
            gap,
            status="REJECTED",
            reviewer_id=reviewer.id,
            reviewer_note=reviewer_note,
        )
        observe_knowledge_gap("rejected", gap.reason)
        return reviewed

    async def _pending_gap(self, gap_id: int) -> KnowledgeGap:
        gap = await self.feedback_repo.get_gap(gap_id)
        if gap is None:
            raise HTTPException(status_code=404, detail="Knowledge gap not found")
        if gap.status != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Knowledge gap has already been reviewed",
            )
        return gap

    async def _question_before(self, message: Message) -> str:
        result = await self.db.execute(
            select(Message)
            .where(
                Message.ticket_id == message.ticket_id,
                Message.sender_type == "CUSTOMER",
                Message.id < message.id,
            )
            .order_by(Message.id.desc())
            .limit(1)
        )
        question = result.scalar_one_or_none()
        return question.content if question else "用户未提供可恢复的问题文本"

    @staticmethod
    def _automatic_reason(
        result: CustomerServiceAgentResult,
        state: AgentState,
        retrieved_knowledge: list[dict],
    ) -> str | None:
        if result.review is not None and not result.review.approved:
            return "reply_review_failed"
        if (
            state.current_step == "waiting_for_human"
            and state.pending_action is None
            and result.action.reason != "prompt_injection_detected"
        ):
            return "agent_handoff"
        if (
            state.category in {"PRODUCT", "COUPON"}
            and result.action.action == "direct_reply"
            and not retrieved_knowledge
        ):
            return "no_knowledge_evidence"
        return None

    @staticmethod
    def _fingerprint(question: str) -> str:
        normalized = re.sub(r"\s+", "", question).lower()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
