from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_admin
from app.db.session import get_db
from app.models.user import User
from app.schemas.knowledge import (
    KnowledgeDocumentCreate,
    KnowledgeDocumentResponse,
    KnowledgeDocumentUpdate,
    KnowledgeIngestResponse,
    KnowledgeSearchRequest,
    RetrievedKnowledgeResponse,
)
from app.services.knowledge_service import KnowledgeAdminService


router = APIRouter(prefix="/knowledge", tags=["Knowledge Base"])


@router.post(
    "",
    response_model=KnowledgeIngestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_knowledge_document(
    data: KnowledgeDocumentCreate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    document, chunk_count = await KnowledgeAdminService(
        db
    ).create_document(data)
    return {"document": document, "chunk_count": chunk_count}


@router.get("", response_model=list[KnowledgeDocumentResponse])
async def list_knowledge_documents(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await KnowledgeAdminService(db).list_documents()


@router.post(
    "/search",
    response_model=list[RetrievedKnowledgeResponse],
)
async def search_knowledge(
    data: KnowledgeSearchRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await KnowledgeAdminService(db).search(
        data.query,
        data.top_k,
    )


@router.put(
    "/{document_id}",
    response_model=KnowledgeIngestResponse,
)
async def update_knowledge_document(
    document_id: int,
    data: KnowledgeDocumentUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    document, chunk_count = await KnowledgeAdminService(
        db
    ).update_document(document_id, data)
    return {"document": document, "chunk_count": chunk_count}


@router.delete(
    "/{document_id}",
    response_model=KnowledgeDocumentResponse,
)
async def deactivate_knowledge_document(
    document_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await KnowledgeAdminService(db).deactivate_document(
        document_id
    )
