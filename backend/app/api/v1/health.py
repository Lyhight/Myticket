from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.operations.rate_limit import check_rate_limit_backend
from app.kb.vector_index import build_vector_index


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
    vector_index_status = "disabled"
    try:
        value = (await db.execute(text("SELECT 1"))).scalar()
        rate_limit_backend = await check_rate_limit_backend()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="A required backend is not ready",
        ) from exc
    vector_index = build_vector_index()
    if vector_index is not None:
        try:
            await vector_index.healthcheck()
            vector_index_status = "qdrant"
        except Exception:
            # RAG has a local-vector and keyword fallback, so a Qdrant outage
            # is degraded service rather than an API-readiness failure.
            vector_index_status = "degraded"
    return {
        "status": "ready",
        "database": value == 1,
        "rate_limit_backend": rate_limit_backend,
        "vector_index": vector_index_status,
    }
