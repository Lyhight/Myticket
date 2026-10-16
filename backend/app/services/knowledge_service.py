from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.rag import (
    HybridKnowledgeRetriever,
    KnowledgeBaseService,
)
from app.repositories.knowledge_repository import KnowledgeRepository
from app.schemas.knowledge import (
    KnowledgeDocumentCreate,
    KnowledgeDocumentUpdate,
)


class KnowledgeAdminService:
    def __init__(self, db: AsyncSession):
        self.repository = KnowledgeRepository(db)
        self.knowledge_base = KnowledgeBaseService(self.repository)
        self.retriever = HybridKnowledgeRetriever(self.repository)

    async def create_document(
        self,
        data: KnowledgeDocumentCreate,
    ):
        chunk_count = await self.knowledge_base.ingest(
            title=data.title,
            source=data.source,
            content=data.content,
        )
        document = await self._get_by_source(data.source)
        return document, chunk_count

    async def list_documents(self):
        return await self.repository.list_documents()

    async def update_document(
        self,
        document_id: int,
        data: KnowledgeDocumentUpdate,
    ):
        document = await self._require_document(document_id)
        chunk_count = await self.knowledge_base.ingest(
            title=data.title,
            source=document.source,
            content=data.content,
        )
        document = await self._require_document(document_id)
        return document, chunk_count

    async def deactivate_document(self, document_id: int):
        document = await self._require_document(document_id)
        return await self.repository.deactivate_document(document)

    async def search(self, query: str, top_k: int):
        return await self.retriever.retrieve(query, top_k=top_k)

    async def _require_document(self, document_id: int):
        document = await self.repository.get_document(document_id)
        if document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Knowledge document not found",
            )
        return document

    async def _get_by_source(self, source: str):
        documents = await self.repository.list_documents()
        for document in documents:
            if document.source == source:
                return document
        raise RuntimeError("Knowledge document was not persisted")
