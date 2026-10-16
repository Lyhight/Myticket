from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.models.message import Message


class MessageRepository:

    def __init__(
        self,
        db: AsyncSession,
    ):
        self.db = db

    async def create(
        self,
        ticket_id: int,
        sender_type: str,
        content: str,
        operation_key: str | None = None,
    ) -> Message:

        if operation_key:
            existing = await self.get_by_operation_key(operation_key)
            if existing:
                return existing

        message = Message(
            ticket_id=ticket_id,
            sender_type=sender_type,
            content=content,
            operation_key=operation_key,
        )

        self.db.add(message)

        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            if operation_key:
                existing = await self.get_by_operation_key(operation_key)
                if existing:
                    return existing
            raise
        await self.db.refresh(message)

        return message

    async def get_by_id(self, message_id: int) -> Message | None:
        return await self.db.get(Message, message_id)

    async def get_by_operation_key(self, operation_key: str) -> Message | None:
        result = await self.db.execute(
            select(Message).where(Message.operation_key == operation_key)
        )
        return result.scalar_one_or_none()

    async def list_by_ticket(
        self,
        ticket_id: int,
    ) -> list[Message]:

        result = await self.db.execute(
            select(Message)
            .where(
                Message.ticket_id == ticket_id
            )
            .order_by(
                Message.created_at.asc()
            )
        )

        return list(
            result.scalars().all()
        )
