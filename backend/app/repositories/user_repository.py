from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.models.user import User


class UserRepository:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(
        self,
        user_id: int,
    ) -> User | None:
        result = await self.db.execute(
            select(User).where(
                User.id == user_id
            )
        )

        return result.scalar_one_or_none()

    async def get_by_email(
        self,
        email: str,
    ) -> User | None:
        result = await self.db.execute(
            select(User).where(
                User.email == email
            )
        )

        return result.scalar_one_or_none()

    async def create(
        self,
        email: str,
        password_hash: str,
    ) -> User:

        user = User(
            email=email,
            password_hash=password_hash,
        )

        self.db.add(user)

        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raise
        await self.db.refresh(user)

        return user
