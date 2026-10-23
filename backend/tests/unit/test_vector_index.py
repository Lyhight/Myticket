import json

import httpx
import pytest

from app.agent.vector_index import QdrantVectorIndex
from app.models.knowledge import KnowledgeChunk


async def test_qdrant_creates_collection_upserts_and_queries() -> None:
    requests: list[tuple[str, str, dict | None]] = []
    collection_exists = False

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal collection_exists
        body = json.loads(request.content) if request.content else None
        requests.append((request.method, request.url.path, body))
        if request.method == "GET":
            if not collection_exists:
                return httpx.Response(404, json={"status": "not found"})
            return httpx.Response(
                200,
                json={
                    "result": {
                        "config": {"params": {"vectors": {"size": 2}}}
                    }
                },
            )
        if request.method == "PUT" and request.url.path.endswith(
            "/collections/test"
        ):
            collection_exists = True
            return httpx.Response(200, json={"status": "ok"})
        if request.url.path.endswith("/points/query"):
            return httpx.Response(
                200,
                json={"result": {"points": [{"id": 7, "score": 0.91}]}},
            )
        return httpx.Response(200, json={"status": "ok"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://qdrant",
    ) as client:
        index = QdrantVectorIndex(
            url="http://qdrant",
            collection="test",
            dimensions=2,
            client=client,
        )
        chunk = KnowledgeChunk(
            id=7,
            document_id=3,
            chunk_index=0,
            content="退款规则",
            content_hash="hash",
            token_count=4,
            embedding=[1.0, 0.0],
            embedding_model="test-model",
        )
        await index.replace_document(3, [chunk])
        hits = await index.search([1.0, 0.0], limit=5)

    assert [(hit.chunk_id, hit.score) for hit in hits] == [(7, 0.91)]
    assert sum(path == "/collections/test" for _, path, _ in requests) == 2
    delete_body = next(
        body for method, path, body in requests
        if method == "POST" and path.endswith("/points/delete")
    )
    assert delete_body["filter"]["must"][0]["match"]["value"] == 3
    upsert_body = next(
        body for method, path, body in requests
        if method == "PUT" and path.endswith("/points")
    )
    assert upsert_body["points"][0]["id"] == 7
    query_body = next(
        body for method, path, body in requests
        if method == "POST" and path.endswith("/points/query")
    )
    assert query_body["params"]["exact"] is False


async def test_qdrant_rejects_collection_dimension_mismatch() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "result": {
                    "config": {"params": {"vectors": {"size": 1024}}}
                }
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://qdrant",
    ) as client:
        index = QdrantVectorIndex(
            url="http://qdrant",
            collection="test",
            dimensions=512,
            client=client,
        )
        with pytest.raises(RuntimeError, match="dimension mismatch"):
            await index.ensure_collection()


async def test_qdrant_validates_query_vector_dimensions() -> None:
    index = QdrantVectorIndex(
        url="http://qdrant",
        collection="test",
        dimensions=2,
    )

    with pytest.raises(ValueError, match="dimension"):
        await index.search([1.0], limit=3)
