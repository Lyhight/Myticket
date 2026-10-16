from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.operations.rate_limit import check_rate_limit_backend


router = APIRouter(
    prefix="/health",
    tags=["Health"],
)


@router.get("")
async def health_check():
    return {
        "status": "ok"
    }


@router.get("/ready")
async def readiness_check(
    db: AsyncSession = Depends(get_db),
):
    try:
        value = (await db.execute(text("SELECT 1"))).scalar()
        rate_limit_backend = await check_rate_limit_backend()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="A required backend is not ready",
        ) from exc
    return {
        "status": "ready",
        "database": value == 1,
        "rate_limit_backend": rate_limit_backend,
    }
