from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feedback import KnowledgeGap, MessageFeedback


class FeedbackRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_message_feedback(
        self, message_id: int, user_id: int
    ) -> MessageFeedback | None:
        result = await self.db.execute(
            select(MessageFeedback).where(
                MessageFeedback.message_id == message_id,
                MessageFeedback.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_ticket_feedback(
        self, ticket_id: int, user_id: int
    ) -> list[MessageFeedback]:
        result = await self.db.execute(
            select(MessageFeedback)
            .where(
                MessageFeedback.ticket_id == ticket_id,
                MessageFeedback.user_id == user_id,
            )
            .order_by(MessageFeedback.id)
        )
        return list(result.scalars())

    async def save_feedback(
        self,
        *,
        ticket_id: int,
        message_id: int,
        agent_run_id: int | None,
        user_id: int,
        rating: str,
        comment: str | None,
    ) -> MessageFeedback:
        feedback = await self.get_message_feedback(message_id, user_id)
        if feedback is None:
            feedback = MessageFeedback(
                ticket_id=ticket_id,
                message_id=message_id,
                agent_run_id=agent_run_id,
                user_id=user_id,
                rating=rating,
                comment=comment,
            )
            self.db.add(feedback)
            await self.db.flush()
        else:
            feedback.rating = rating
            feedback.comment = comment
            feedback.agent_run_id = agent_run_id
        return feedback

    async def upsert_gap(
        self,
        *,
        fingerprint: str,
        ticket_id: int | None,
        agent_run_id: int | None,
        feedback_id: int | None,
        question: str,
        suggested_answer: str | None,
        source: str,
        reason: str,
    ) -> KnowledgeGap:
        result = await self.db.execute(
            select(KnowledgeGap).where(KnowledgeGap.fingerprint == fingerprint)
        )
        gap = result.scalar_one_or_none()
        if gap is None:
            gap = KnowledgeGap(
                fingerprint=fingerprint,
                ticket_id=ticket_id,
                agent_run_id=agent_run_id,
                feedback_id=feedback_id,
                question=question,
                suggested_answer=suggested_answer,
                source=source,
                reason=reason,
            )
            self.db.add(gap)
            await self.db.flush()
        else:
            gap.occurrence_count += 1
            gap.ticket_id = ticket_id or gap.ticket_id
            gap.agent_run_id = agent_run_id or gap.agent_run_id
            gap.feedback_id = feedback_id or gap.feedback_id
            gap.suggested_answer = suggested_answer or gap.suggested_answer
            if gap.status == "REJECTED":
                gap.status = "PENDING"
                gap.reviewed_by = None
                gap.reviewed_at = None
                gap.reviewer_note = None
        return gap

    async def get_gap(self, gap_id: int) -> KnowledgeGap | None:
        return await self.db.get(KnowledgeGap, gap_id)

    async def list_gaps(self, status: str | None) -> list[KnowledgeGap]:
        statement = select(KnowledgeGap)
        if status:
            statement = statement.where(KnowledgeGap.status == status)
        result = await self.db.execute(
            statement.order_by(
                KnowledgeGap.occurrence_count.desc(),
                KnowledgeGap.updated_at.desc(),
            )
        )
        return list(result.scalars())

    async def mark_reviewed(
        self,
        gap: KnowledgeGap,
        *,
        status: str,
        reviewer_id: int,
        reviewer_note: str | None,
        knowledge_document_id: int | None = None,
    ) -> KnowledgeGap:
        gap.status = status
        gap.reviewed_by = reviewer_id
        gap.reviewer_note = reviewer_note
        gap.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        gap.knowledge_document_id = knowledge_document_id
        await self.db.commit()
        await self.db.refresh(gap)
        return gap
