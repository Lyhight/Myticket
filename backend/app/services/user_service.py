from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.core.security import hash_password
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate


class UserService:

    def __init__(self, db: AsyncSession):
        self.repo = UserRepository(db)

    async def create_user(
        self,
        data: UserCreate,
    ):
        existing = await self.repo.get_by_email(
            data.email
        )

        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )

        password_hash = hash_password(
            data.password
        )

        try:
            return await self.repo.create(
                email=data.email,
                password_hash=password_hash,
            )
        except IntegrityError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            ) from exc
