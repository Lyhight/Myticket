import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from app.core.config import settings
from app.models.knowledge import KnowledgeChunk


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class VectorSearchHit:
    chunk_id: int
    score: float


class QdrantVectorIndex:
    """Small async Qdrant adapter used by the RAG layer.

    MySQL remains the source of truth. Qdrant stores only vectors and stable
    identifiers, so retrieved content is always reloaded from the active MySQL
    records before it is exposed to the Agent.
    """

    def __init__(
        self,
        *,
        url: str,
        collection: str,
        dimensions: int,
        api_key: str = "",
        timeout_seconds: float = 5.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.url = url.rstrip("/")
        self.collection = collection
        self.dimensions = dimensions
        self.timeout_seconds = timeout_seconds
        self._external_client = client
        self._headers = {"api-key": api_key} if api_key else {}
        self._collection_ready = False

    @property
    def _collection_path(self) -> str:
        return f"/collections/{quote(self.collection, safe='')}"

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> httpx.Response:
        if self._external_client is not None:
            return await self._external_client.request(
                method,
                path,
                headers=self._headers,
                json=json,
            )
        async with httpx.AsyncClient(
            base_url=self.url,
            timeout=self.timeout_seconds,
            headers=self._headers,
        ) as client:
            return await client.request(method, path, json=json)

    async def ensure_collection(self) -> None:
        if self._collection_ready:
            return
        response = await self._request("GET", self._collection_path)
        if response.status_code == 404:
            created = await self._request(
                "PUT",
                self._collection_path,
                json={
                    "vectors": {
                        "size": self.dimensions,
                        "distance": "Cosine",
                    },
                    "hnsw_config": {
                        "m": settings.qdrant_hnsw_m,
                        "ef_construct": settings.qdrant_hnsw_ef_construct,
                    },
                },
            )
            created.raise_for_status()
            self._collection_ready = True
            return
        response.raise_for_status()
        payload = response.json()
        vectors = (
            payload.get("result", {})
            .get("config", {})
            .get("params", {})
            .get("vectors", {})
        )
        actual_dimensions = vectors.get("size")
        if actual_dimensions != self.dimensions:
            raise RuntimeError(
                "Qdrant collection dimension mismatch: "
                f"expected {self.dimensions}, got {actual_dimensions}"
            )
        self._collection_ready = True

    async def healthcheck(self) -> None:
        await self.ensure_collection()

    async def replace_document(
        self,
        document_id: int,
        chunks: list[KnowledgeChunk],
    ) -> None:
        await self.ensure_collection()
        await self.delete_document(document_id, ensure=False)
        points = [
            {
                "id": chunk.id,
                "vector": chunk.embedding,
                "payload": {
                    "document_id": document_id,
                    "chunk_index": chunk.chunk_index,
                    "embedding_model": chunk.embedding_model,
                },
            }
            for chunk in chunks
            if chunk.embedding is not None
        ]
        if not points:
            return
        response = await self._request(
            "PUT",
            f"{self._collection_path}/points?wait=true",
            json={"points": points},
        )
        response.raise_for_status()

    async def delete_document(
        self,
        document_id: int,
        *,
        ensure: bool = True,
    ) -> None:
        if ensure:
            await self.ensure_collection()
        response = await self._request(
            "POST",
            f"{self._collection_path}/points/delete?wait=true",
            json={
                "filter": {
                    "must": [
                        {
                            "key": "document_id",
                            "match": {"value": document_id},
                        }
                    ]
                }
            },
        )
        response.raise_for_status()

    async def search(
        self,
        vector: list[float],
        *,
        limit: int,
        score_threshold: float = 0.0,
    ) -> list[VectorSearchHit]:
        if len(vector) != self.dimensions:
            raise ValueError(
                "query embedding dimension does not match Qdrant collection"
            )
        await self.ensure_collection()
        response = await self._request(
            "POST",
            f"{self._collection_path}/points/query",
            json={
                "query": vector,
                "limit": limit,
                "score_threshold": score_threshold,
                "with_payload": False,
                "with_vector": False,
                "params": {
                    "hnsw_ef": settings.qdrant_hnsw_ef_search,
                    "exact": False,
                },
            },
        )
        response.raise_for_status()
        points = response.json().get("result", {}).get("points", [])
        return [
            VectorSearchHit(
                chunk_id=int(point["id"]),
                score=float(point["score"]),
            )
            for point in points
        ]


def build_vector_index() -> QdrantVectorIndex | None:
    if not settings.qdrant_enabled:
        return None
    return QdrantVectorIndex(
        url=settings.qdrant_url,
        collection=settings.qdrant_collection,
        dimensions=settings.embedding_dimensions,
        api_key=settings.qdrant_api_key,
        timeout_seconds=settings.qdrant_timeout_seconds,
    )
