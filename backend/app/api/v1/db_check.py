from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db


router = APIRouter(
    prefix="/db-check",
    tags=["Database"],
)


@router.get("")
async def db_check(
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        text("SELECT 1")
    )

    value = result.scalar()

    return {
        "database": "connected",
        "result": value,
    }