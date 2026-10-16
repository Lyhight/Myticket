from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.auth import (
    LoginRequest,
    TokenResponse,
)
from app.services.auth_service import AuthService
from app.core.config import settings
from app.operations.rate_limit import create_rate_limiter


router = APIRouter(
    prefix="/auth",
    tags=["Auth"],
)

auth_account_rate_limiter = create_rate_limiter(
    limit=settings.auth_account_rate_limit_per_minute,
    window_seconds=60,
    detail="Too many login attempts",
)
auth_ip_rate_limiter = create_rate_limiter(
    limit=settings.auth_ip_rate_limit_per_minute,
    window_seconds=60,
    detail="Too many login attempts",
)


@router.post(
    "/login",
    response_model=TokenResponse,
)
async def login(
    data: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    client_host = request.client.host if request.client else "unknown"
    await auth_ip_rate_limiter.consume(f"ip:{client_host}")
    await auth_account_rate_limiter.consume(
        f"account:{str(data.email).lower()}"
    )
    service = AuthService(db)

    token_response = await service.login(data)
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token_response.access_token,
        max_age=settings.access_token_expire_minutes * 60,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="strict",
        path="/api",
    )
    return token_response


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    response.delete_cookie(
        key=settings.auth_cookie_name,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="strict",
        path="/api",
    )
