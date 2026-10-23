from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain_event import DomainEvent


SUPPORT_ROLES = {"agent", "supervisor", "admin"}


class EventRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def append(
        self,
        *,
        event_type: str,
        aggregate_id: int,
        payload: dict,
        audience_role: str | None = None,
        audience_user_id: int | None = None,
        commit: bool = True,
    ) -> DomainEvent:
        event = DomainEvent(
            event_type=event_type,
            aggregate_type="ticket",
            aggregate_id=aggregate_id,
            audience_role=audience_role,
            audience_user_id=audience_user_id,
            payload=payload,
        )
        self.db.add(event)
        if commit:
            await self.db.commit()
            await self.db.refresh(event)
        else:
            await self.db.flush()
        return event

    async def list_after(
        self,
        *,
        event_id: int,
        user_id: int,
        role: str,
        limit: int = 100,
    ) -> list[DomainEvent]:
        roles = {role}
        if role in {"supervisor", "admin"}:
            roles.update(SUPPORT_ROLES)
        result = await self.db.execute(
            select(DomainEvent)
            .where(
                DomainEvent.id > event_id,
                or_(
                    DomainEvent.audience_user_id == user_id,
                    DomainEvent.audience_role.in_(roles),
                    DomainEvent.audience_role == "*",
                ),
            )
            .order_by(DomainEvent.id)
            .limit(limit)
        )
        return list(result.scalars().all())
