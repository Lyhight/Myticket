from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.message import Message
from app.models.agent_run import AgentRun
from app.models.agent_task import AgentTask
from app.models.ticket import Ticket
from app.models.user_memory import UserMemory
from app.models.domain_event import DomainEvent
from datetime import datetime, timezone


class TicketRepository:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        user_id: int,
        title: str,
        content: str,
    ) -> Ticket:
        """
        创建工单，并同时创建第一条用户消息。
        """

        ticket = Ticket(
            user_id=user_id,
            title=title,
        )

        self.db.add(ticket)

        # flush 不会提交事务，但会让 ticket.id 生成出来
        await self.db.flush()

        message = Message(
            ticket_id=ticket.id,
            sender_type="CUSTOMER",
            content=content,
        )

        self.db.add(message)

        await self.db.commit()
        await self.db.refresh(ticket)

        return ticket

    async def list_by_user(
        self,
        user_id: int,
    ) -> list[Ticket]:
        """
        查询某个用户的全部工单。
        """

        result = await self.db.execute(
            select(Ticket)
            .where(Ticket.user_id == user_id)
            .order_by(Ticket.created_at.desc())
        )

        return list(result.scalars().all())

    async def get_by_id(
        self,
        ticket_id: int,
    ) -> Ticket | None:
        """
        根据工单 ID 查询工单，
        并同时加载该工单下的全部消息。
        """

        result = await self.db.execute(
            select(Ticket)
            .options(selectinload(Ticket.messages))
            .where(Ticket.id == ticket_id)
        )

        return result.scalar_one_or_none()

    async def delete(self, ticket: Ticket) -> None:
        """删除工单、对话、执行轨迹和由该工单提取的记忆。"""
        await self.db.execute(
            delete(UserMemory).where(UserMemory.source_ticket_id == ticket.id)
        )
        await self.db.execute(
            delete(AgentRun).where(AgentRun.ticket_id == ticket.id)
        )
        # AgentTask.result_message_id also references messages. Delete tasks
        # before the ORM cascades message deletion to avoid an FK violation.
        await self.db.execute(
            delete(AgentTask).where(AgentTask.ticket_id == ticket.id)
        )
        await self.db.execute(
            delete(DomainEvent).where(
                DomainEvent.aggregate_type == "ticket",
                DomainEvent.aggregate_id == ticket.id,
            )
        )
        await self.db.delete(ticket)
        await self.db.commit()
    async def update_classification(
        self,
        ticket: Ticket,
        category: str,
        priority: str,
        intent: str,
        route_to: str,
        source: str,
        attempts: int,
        latency_ms: float,
        fallback_used: bool,
    ) -> Ticket:

        ticket.category = category
        ticket.priority = priority
        ticket.intent = intent
        ticket.route_to = route_to

        ticket.classification_source = source
        ticket.classification_attempts = attempts
        ticket.classification_latency_ms = latency_ms
        ticket.classification_fallback_used = fallback_used
        ticket.classified_at = datetime.now(
            timezone.utc
        ).replace(tzinfo=None)

        await self.db.commit()
        await self.db.refresh(ticket)

        return ticket

    async def set_status(
        self,
        ticket: Ticket,
        status: str,
        *,
        event_type: str | None = None,
        event_payload: dict | None = None,
        audience_role: str | None = None,
        audience_user_id: int | None = None,
        escalation_reason: str | None = None,
    ) -> Ticket:
        """
        更新工单状态。
        """

        ticket.status = status
        if escalation_reason is not None:
            ticket.escalation_reason = escalation_reason
        if status == "RESOLVED":
            ticket.resolved_at = datetime.now(timezone.utc).replace(tzinfo=None)
        if event_type:
            self.db.add(DomainEvent(
                event_type=event_type,
                aggregate_type="ticket",
                aggregate_id=ticket.id,
                audience_role=audience_role,
                audience_user_id=audience_user_id,
                payload=event_payload or {"ticket_id": ticket.id},
            ))

        await self.db.commit()
        await self.db.refresh(ticket)

        return ticket

    async def claim_version(
        self,
        ticket: Ticket,
        expected_version: int,
    ) -> bool:
        """原子占用本轮状态版本；失败说明另一个请求已先处理。"""
        result = await self.db.execute(
            update(Ticket)
            .where(
                Ticket.id == ticket.id,
                Ticket.version == expected_version,
            )
            .values(version=Ticket.version + 1)
        )
        await self.db.commit()

        if result.rowcount != 1:
            return False

        await self.db.refresh(ticket)
        return True

    async def list_pending(
        self,
    ) -> list[Ticket]:
        """
        查询所有待人工审批的工单。
        """

        result = await self.db.execute(
            select(Ticket)
            .where(Ticket.status == "PENDING_REVIEW")
            .order_by(Ticket.created_at.asc())
        )

        return list(result.scalars().all())

    async def list_handoff_queue(self) -> list[Ticket]:
        result = await self.db.execute(
            select(Ticket)
            .where(Ticket.status == "WAITING_HUMAN")
            .order_by(Ticket.created_at.asc())
        )
        return list(result.scalars().all())

    async def list_assigned(self, agent_id: int) -> list[Ticket]:
        result = await self.db.execute(
            select(Ticket)
            .where(
                Ticket.assigned_agent_id == agent_id,
                Ticket.status == "HUMAN_PROCESSING",
            )
            .order_by(Ticket.claimed_at.asc())
        )
        return list(result.scalars().all())

    async def claim_for_agent(self, ticket_id: int, agent_id: int) -> Ticket | None:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        result = await self.db.execute(
            update(Ticket)
            .where(
                Ticket.id == ticket_id,
                Ticket.status == "WAITING_HUMAN",
                Ticket.assigned_agent_id.is_(None),
            )
            .values(
                status="HUMAN_PROCESSING",
                assigned_agent_id=agent_id,
                claimed_at=now,
                human_started_at=now,
                version=Ticket.version + 1,
            )
        )
        if result.rowcount != 1:
            await self.db.rollback()
            return None
        ticket = await self.db.get(Ticket, ticket_id)
        self.db.add(DomainEvent(
            event_type="ticket.claimed",
            aggregate_type="ticket",
            aggregate_id=ticket_id,
            audience_role="agent",
            audience_user_id=ticket.user_id,
            payload={"ticket_id": ticket_id, "agent_id": agent_id},
        ))
        await self.db.commit()
        await self.db.refresh(ticket)
        return ticket
