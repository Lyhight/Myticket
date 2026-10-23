import asyncio

from app.kb.embeddings import DashScopeEmbeddingClient
from app.kb.vector_index import build_vector_index
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.repositories.knowledge_repository import KnowledgeRepository


async def reindex() -> None:
    vector_index = build_vector_index()
    if vector_index is None:
        raise RuntimeError(
            "Set EMBEDDING_ENABLED=true and QDRANT_ENABLED=true before reindexing"
        )
    embedding_client = DashScopeEmbeddingClient()
    document_count = 0
    chunk_count = 0
    async with AsyncSessionLocal() as db:
        repository = KnowledgeRepository(db)
        for document in await repository.list_documents():
            if not document.is_active:
                await vector_index.delete_document(document.id)
                continue
            chunks = await repository.list_document_chunks(document.id)
            stale = [
                chunk
                for chunk in chunks
                if chunk.embedding is None
                or chunk.embedding_model != settings.embedding_model
                or len(chunk.embedding) != settings.embedding_dimensions
            ]
            if stale:
                embeddings = await embedding_client.embed(
                    [chunk.content for chunk in stale]
                )
                await repository.update_chunk_embeddings(
                    stale,
                    embeddings,
                    embedding_model=settings.embedding_model,
                )
            await vector_index.replace_document(document.id, chunks)
            document_count += 1
            chunk_count += len(chunks)
    print(
        f"Qdrant reindex complete: {document_count} document(s), "
        f"{chunk_count} chunk(s)"
    )


if __name__ == "__main__":
    asyncio.run(reindex())
