from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from app.models.knowledge import KnowledgeChunk, KnowledgeDocument


class KnowledgeRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_document(
        self,
        document_id: int,
    ) -> KnowledgeDocument | None:
        result = await self.db.execute(
            select(KnowledgeDocument).where(
                KnowledgeDocument.id == document_id
            )
        )
        return result.scalar_one_or_none()

    async def list_documents(self) -> list[KnowledgeDocument]:
        result = await self.db.execute(
            select(KnowledgeDocument).order_by(
                KnowledgeDocument.updated_at.desc(),
                KnowledgeDocument.id.desc(),
            )
        )
        return list(result.scalars().all())

    async def deactivate_document(
        self,
        document: KnowledgeDocument,
    ) -> KnowledgeDocument:
        document.is_active = False
        await self.db.commit()
        await self.db.refresh(document)
        return document

    async def replace_document(
        self,
        *,
        title: str,
        source: str,
        chunks: list[str],
        embeddings: list[list[float]] | None = None,
        embedding_model: str | None = None,
        content_hash: str,
        chunk_hashes: list[str],
        token_counts: list[int],
    ) -> KnowledgeDocument:
        result = await self.db.execute(
            select(KnowledgeDocument).where(
                KnowledgeDocument.source == source
            )
        )
        document = result.scalar_one_or_none()

        if document is None:
            document = KnowledgeDocument(
                title=title,
                source=source,
                version=1,
                content_hash=content_hash,
            )
            self.db.add(document)
            await self.db.flush()
        else:
            if (
                document.content_hash == content_hash
                and document.is_active
            ):
                return document
            document.title = title
            document.is_active = True
            document.version += 1
            document.content_hash = content_hash
            await self.db.execute(
                delete(KnowledgeChunk).where(
                    KnowledgeChunk.document_id == document.id
                )
            )

        self.db.add_all(
            KnowledgeChunk(
                document_id=document.id,
                chunk_index=index,
                content=content,
                content_hash=chunk_hashes[index],
                token_count=token_counts[index],
                embedding=(
                    embeddings[index]
                    if embeddings and index < len(embeddings)
                    else None
                ),
                embedding_model=(
                    embedding_model if embeddings else None
                ),
            )
            for index, content in enumerate(chunks)
        )
        await self.db.commit()
        await self.db.refresh(document)
        return document

    async def update_chunk_embeddings(
        self,
        chunks: list[KnowledgeChunk],
        embeddings: list[list[float]],
        *,
        embedding_model: str,
    ) -> None:
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            chunk.embedding = embedding
            chunk.embedding_model = embedding_model
        await self.db.commit()

    async def list_document_chunks(
        self,
        document_id: int,
    ) -> list[KnowledgeChunk]:
        result = await self.db.execute(
            select(KnowledgeChunk)
            .where(KnowledgeChunk.document_id == document_id)
            .order_by(KnowledgeChunk.chunk_index)
        )
        return list(result.scalars().all())

    async def get_active_chunks_by_ids(
        self,
        chunk_ids: list[int],
    ) -> list[tuple[KnowledgeChunk, KnowledgeDocument]]:
        if not chunk_ids:
            return []
        result = await self.db.execute(
            select(KnowledgeChunk, KnowledgeDocument)
            .join(
                KnowledgeDocument,
                KnowledgeDocument.id == KnowledgeChunk.document_id,
            )
            .where(
                KnowledgeChunk.id.in_(chunk_ids),
                KnowledgeDocument.is_active.is_(True),
            )
        )
        rows_by_id = {
            chunk.id: (chunk, document)
            for chunk, document in result.all()
        }
        return [
            rows_by_id[chunk_id]
            for chunk_id in chunk_ids
            if chunk_id in rows_by_id
        ]

    async def list_active_chunks(
        self,
        *,
        limit: int | None = None,
        include_embeddings: bool = True,
    ) -> list[tuple[KnowledgeChunk, KnowledgeDocument]]:
        statement = (
            select(KnowledgeChunk, KnowledgeDocument)
            .join(
                KnowledgeDocument,
                KnowledgeDocument.id == KnowledgeChunk.document_id,
            )
            .where(KnowledgeDocument.is_active.is_(True))
            .order_by(KnowledgeDocument.id, KnowledgeChunk.chunk_index)
        )
        if not include_embeddings:
            statement = statement.options(defer(KnowledgeChunk.embedding))
        if limit is not None:
            statement = statement.limit(limit)
        result = await self.db.execute(statement)
        return list(result.all())
