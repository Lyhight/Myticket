from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.agent.embedding import DashScopeEmbeddingClient


async def test_embedding_client_batches_without_changing_order() -> None:
    client = DashScopeEmbeddingClient.__new__(DashScopeEmbeddingClient)
    create = AsyncMock()

    async def fake_create(*, model, input, dimensions):
        return SimpleNamespace(data=[
            SimpleNamespace(index=index, embedding=[float(value)])
            for index, value in reversed(list(enumerate(input)))
        ])

    create.side_effect = fake_create
    client.client = SimpleNamespace(
        embeddings=SimpleNamespace(create=create),
    )
    client.model = "test-model"
    client.dimensions = 1
    client.timeout_seconds = 1
    client.batch_size = 10

    result = await client.embed([str(index) for index in range(23)])

    assert result == [[float(index)] for index in range(23)]
    assert [len(call.kwargs["input"]) for call in create.await_args_list] == [
        10,
        10,
        3,
    ]
