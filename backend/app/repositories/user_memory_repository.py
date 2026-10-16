from datetime import datetime, timezone

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_memory import UserMemory


class UserMemoryRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_active_by_user(
        self,
        user_id: int,
        *,
        limit: int = 10,
    ) -> list[UserMemory]:
        result = await self.db.execute(
            select(UserMemory)
            .where(
                UserMemory.user_id == user_id,
                UserMemory.is_active.is_(True),
                or_(
                    UserMemory.expires_at.is_(None),
                    UserMemory.expires_at
                    > datetime.now(timezone.utc).replace(tzinfo=None),
                ),
            )
            .order_by(UserMemory.updated_at.desc())
            .limit(limit)
        )
        memories = list(result.scalars().all())
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for memory in memories:
            memory.last_accessed_at = now
        if memories:
            await self.db.commit()
        return memories

    async def deactivate_conflicts(
        self,
        *,
        user_id: int,
        memory_key: str,
        keep_fingerprint: str,
    ) -> None:
        await self.db.execute(
            update(UserMemory)
            .where(
                UserMemory.user_id == user_id,
                UserMemory.memory_key == memory_key,
                UserMemory.fingerprint != keep_fingerprint,
                UserMemory.is_active.is_(True),
            )
            .values(is_active=False)
        )

    async def upsert(
        self,
        *,
        user_id: int,
        memory_type: str,
        content: str,
        fingerprint: str,
        memory_key: str,
        source_ticket_id: int | None,
        confidence: float = 1.0,
        expires_at: datetime | None = None,
    ) -> UserMemory:
        result = await self.db.execute(
            select(UserMemory).where(
                UserMemory.user_id == user_id,
                UserMemory.fingerprint == fingerprint,
            )
        )
        memory = result.scalar_one_or_none()

        if memory is None:
            memory = UserMemory(
                user_id=user_id,
                memory_type=memory_type,
                content=content,
                fingerprint=fingerprint,
                memory_key=memory_key,
                source_ticket_id=source_ticket_id,
                confidence=confidence,
                expires_at=expires_at,
            )
            self.db.add(memory)
        else:
            memory.memory_type = memory_type
            memory.content = content
            memory.source_ticket_id = source_ticket_id
            memory.confidence = confidence
            memory.memory_key = memory_key
            memory.expires_at = expires_at
            memory.is_active = True

        await self.db.commit()
        await self.db.refresh(memory)
        return memory
