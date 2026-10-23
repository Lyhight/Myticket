import re
import logging
import hashlib
import asyncio
from dataclasses import dataclass

from app.repositories.knowledge_repository import KnowledgeRepository
from app.kb.embeddings import (
    DashScopeEmbeddingClient,
    cosine_similarity,
)
from app.core.config import settings
from app.kb.vector_index import QdrantVectorIndex, build_vector_index
from app.kb.chunking import KnowledgeChunker


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RetrievedKnowledge:
    chunk_id: int
    title: str
    source: str
    content: str
    score: float
    document_version: int
    chunk_index: int

    def as_context(self) -> dict[str, str | int | float]:
        return {
            "chunk_id": self.chunk_id,
            "title": self.title,
            "source": self.source,
            "content": self.content,
            "score": self.score,
            "document_version": self.document_version,
            "chunk_index": self.chunk_index,
            "citation_id": f"KB-{self.chunk_id}-v{self.document_version}",
        }


class KeywordKnowledgeRetriever:
    """可替换的关键词检索基线，返回带来源的 Top-K 知识片段。"""

    def __init__(self, repository: KnowledgeRepository):
        self.repository = repository

    @staticmethod
    def _terms(query: str) -> set[str]:
        lowered = query.lower()
        terms = set(re.findall(r"[a-z0-9_]{2,}", lowered))
        chinese_groups = re.findall(r"[\u4e00-\u9fff]{2,}", lowered)
        for group in chinese_groups:
            terms.add(group)
            terms.update(
                group[index : index + 2]
                for index in range(len(group) - 1)
            )
        return {term for term in terms if term.strip()}

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int = 3,
        min_score: float = 2.0,
    ) -> list[dict[str, str | int | float]]:
        terms = self._terms(query)
        if not terms:
            return []

        candidates = await self.repository.list_active_chunks(
            include_embeddings=False
        )
        scored: list[RetrievedKnowledge] = []
        for chunk, document in candidates:
            haystack = f"{document.title}\n{chunk.content}".lower()
            matched = [term for term in terms if term in haystack]
            if not matched:
                continue
            score = sum(
                (2.0 if len(term) > 2 else 1.0)
                * haystack.count(term)
                for term in matched
            )
            scored.append(
                RetrievedKnowledge(
                    chunk_id=chunk.id,
                    title=document.title,
                    source=document.source,
                    content=chunk.content,
                    score=score,
                    document_version=document.version,
                    chunk_index=chunk.chunk_index,
                )
            )

        scored.sort(key=lambda item: (-item.score, item.chunk_id))
        unique: list[RetrievedKnowledge] = []
        seen_content: set[str] = set()
        for item in scored:
            if item.score < min_score:
                continue
            fingerprint = hashlib.sha256(
                " ".join(item.content.split()).lower().encode("utf-8")
            ).hexdigest()
            if fingerprint in seen_content:
                continue
            seen_content.add(fingerprint)
            unique.append(item)
            if len(unique) >= top_k:
                break
        return [
            {**item.as_context(), "retrieval_method": "keyword"}
            for item in unique
        ]


class HybridKnowledgeRetriever:
    """融合关键词和向量相似度；向量服务失败时安全降级。"""

    def __init__(
        self,
        repository: KnowledgeRepository,
        *,
        embedding_client: DashScopeEmbeddingClient | None = None,
        keyword_weight: float = 0.4,
        vector_weight: float = 0.6,
        vector_index: QdrantVectorIndex | None = None,
    ) -> None:
        self.repository = repository
        self.keyword = KeywordKnowledgeRetriever(repository)
        self.embedding_client = embedding_client or (
            DashScopeEmbeddingClient()
            if settings.embedding_enabled
            else None
        )
        self.keyword_weight = keyword_weight
        self.vector_weight = vector_weight
        self.vector_index = vector_index or build_vector_index()

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int = 3,
        min_score: float = 0.12,
    ) -> list[dict[str, str | int | float]]:
        keyword_results = await self.keyword.retrieve(
            query,
            top_k=max(top_k * 3, 10),
        )
        if self.embedding_client is None:
            return keyword_results[:top_k]

        try:
            query_vectors = await self.embedding_client.embed([query])
            if not query_vectors:
                return self._mark_fallback(keyword_results[:top_k])
        except Exception as exc:
            logger.warning(
                "Embedding query failed; using keyword retrieval: %s",
                exc,
            )
            return self._mark_fallback(keyword_results[:top_k])

        query_vector = query_vectors[0]
        vector_backend = "local_scan"
        vector_scores: dict[int, float] = {}
        if self.vector_index is not None:
            try:
                hits = await self.vector_index.search(
                    query_vector,
                    limit=max(top_k * 3, settings.rag_candidate_k),
                )
                vector_scores = {
                    hit.chunk_id: max(0.0, hit.score)
                    for hit in hits
                }
                candidates = await self.repository.get_active_chunks_by_ids(
                    list(vector_scores)
                )
                vector_backend = "qdrant_hnsw"
            except Exception as exc:
                logger.warning(
                    "Qdrant search failed; using local vector scan: %s",
                    exc,
                )
                candidates = await self.repository.list_active_chunks()
                vector_backend = "local_scan_fallback"
        else:
            candidates = await self.repository.list_active_chunks()
        keyword_max = max(
            (float(item["score"]) for item in keyword_results),
            default=1.0,
        )
        combined: dict[int, dict[str, str | int | float]] = {}

        for item in keyword_results:
            chunk_id = int(item["chunk_id"])
            combined[chunk_id] = {
                **item,
                "keyword_score": float(item["score"]) / keyword_max,
                "vector_score": 0.0,
            }

        for chunk, document in candidates:
            if not chunk.embedding:
                continue
            vector_score = vector_scores.get(chunk.id)
            if vector_score is None:
                vector_score = max(
                    0.0,
                    cosine_similarity(query_vector, chunk.embedding),
                )
            item = combined.setdefault(
                chunk.id,
                {
                    "chunk_id": chunk.id,
                    "title": document.title,
                    "source": document.source,
                    "content": chunk.content,
                    "document_version": document.version,
                    "chunk_index": chunk.chunk_index,
                    "citation_id": f"KB-{chunk.id}-v{document.version}",
                    "keyword_score": 0.0,
                    "vector_score": 0.0,
                },
            )
            item["vector_score"] = vector_score

        for item in combined.values():
            item["score"] = round(
                self.keyword_weight * float(item["keyword_score"])
                + self.vector_weight * float(item["vector_score"]),
                6,
            )
            item["retrieval_method"] = "hybrid"
            item["vector_backend"] = vector_backend

        ranked = sorted(
            combined.values(),
            key=lambda item: (-float(item["score"]), int(item["chunk_id"])),
        )
        unique: list[dict[str, str | int | float]] = []
        seen_content: set[str] = set()
        for item in ranked:
            if float(item["score"]) < min_score:
                continue
            fingerprint = hashlib.sha256(
                " ".join(str(item["content"]).split())
                .lower()
                .encode("utf-8")
            ).hexdigest()
            if fingerprint in seen_content:
                continue
            seen_content.add(fingerprint)
            unique.append(item)
            if len(unique) >= top_k:
                break
        return unique

    @staticmethod
    def _mark_fallback(
        results: list[dict[str, str | int | float]],
    ) -> list[dict[str, str | int | float]]:
        return [
            {**item, "retrieval_method": "keyword_fallback"}
            for item in results
        ]


class KnowledgeBaseService:
    def __init__(
        self,
        repository: KnowledgeRepository,
        *,
        embedding_client: DashScopeEmbeddingClient | None = None,
        vector_index: QdrantVectorIndex | None = None,
    ):
        self.repository = repository
        self.chunker = KnowledgeChunker(
            chunk_size=settings.knowledge_chunk_size,
            overlap=settings.knowledge_chunk_overlap,
        )
        self.embedding_client = embedding_client or (
            DashScopeEmbeddingClient()
            if settings.embedding_enabled
            else None
        )
        self.vector_index = vector_index or build_vector_index()

    async def ingest(
        self,
        *,
        title: str,
        source: str,
        content: str,
    ) -> int:
        chunks = self.chunker.split(content)
        if not chunks:
            raise ValueError("knowledge document is empty")
        if len(chunks) > settings.knowledge_max_chunks:
            raise ValueError(
                "knowledge document produced too many chunks; split the document"
            )
        embeddings = None
        if self.embedding_client is not None:
            try:
                embeddings = await asyncio.wait_for(
                    self.embedding_client.embed(chunks),
                    timeout=settings.knowledge_embedding_total_timeout_seconds,
                )
            except Exception as exc:
                logger.warning(
                    "Chunk embedding failed; storing keyword-only chunks: %s",
                    exc,
                )
        normalized_content = "\n".join(
            line.strip() for line in content.splitlines() if line.strip()
        )
        content_hash = hashlib.sha256(
            normalized_content.encode("utf-8")
        ).hexdigest()
        document = await self.repository.replace_document(
            title=title,
            source=source,
            chunks=chunks,
            embeddings=embeddings,
            embedding_model=(
                self.embedding_client.model
                if embeddings and self.embedding_client
                else None
            ),
            content_hash=content_hash,
            chunk_hashes=[
                hashlib.sha256(chunk.encode("utf-8")).hexdigest()
                for chunk in chunks
            ],
            token_counts=[max(1, len(chunk) // 2) for chunk in chunks],
        )
        if self.vector_index is not None:
            try:
                stored_chunks = await self.repository.list_document_chunks(
                    document.id
                )
                await self.vector_index.replace_document(
                    document.id,
                    stored_chunks,
                )
            except Exception as exc:
                # MySQL is authoritative. Retrieval will ignore stale point IDs
                # and fall back to local vectors/keywords until a reindex runs.
                logger.warning(
                    "Qdrant document sync failed; MySQL copy remains usable: %s",
                    exc,
                )
        return len(chunks)

    async def deactivate(self, document) -> None:
        if self.vector_index is None:
            return
        try:
            await self.vector_index.delete_document(document.id)
        except Exception as exc:
            logger.warning(
                "Qdrant document delete failed; inactive MySQL chunks remain filtered: %s",
                exc,
            )

