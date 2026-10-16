from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.repositories.user_repository import UserRepository
from app.schemas.auth import LoginRequest, TokenResponse


_DUMMY_PASSWORD_HASH = hash_password(
    "dummy-password-used-only-for-timing-equalization"
)


class AuthService:

    def __init__(self, db: AsyncSession):
        self.repo = UserRepository(db)

    async def login(
        self,
        data: LoginRequest,
    ) -> TokenResponse:

        user = await self.repo.get_by_email(
            data.email
        )

        if user is None:
            # Perform one real password verification so unknown-account and
            # wrong-password responses have similar computational cost.
            verify_password(data.password, _DUMMY_PASSWORD_HASH)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        if not verify_password(
            data.password,
            user.password_hash,
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is inactive",
            )

        token = create_access_token(
            subject=str(user.id),
            extra_claims={
                "role": user.role,
            },
        )

        return TokenResponse(access_token=token)
