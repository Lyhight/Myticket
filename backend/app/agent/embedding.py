import asyncio
import math
from collections.abc import Sequence

from openai import AsyncOpenAI

from app.core.config import settings


class DashScopeEmbeddingClient:
    def __init__(self, *, batch_size: int = 10) -> None:
        if not 1 <= batch_size <= 10:
            raise ValueError("batch_size must be between 1 and 10")
        self.client = AsyncOpenAI(
            api_key=settings.dashscope_api_key,
            base_url=settings.qwen_base_url,
        )
        self.model = settings.embedding_model
        self.dimensions = settings.embedding_dimensions
        self.timeout_seconds = settings.embedding_timeout_seconds
        self.batch_size = batch_size

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        embeddings: list[list[float]] = []
        values = list(texts)
        for start in range(0, len(values), self.batch_size):
            batch = values[start : start + self.batch_size]
            response = await asyncio.wait_for(
                self.client.embeddings.create(
                    model=self.model,
                    input=batch,
                    dimensions=self.dimensions,
                ),
                timeout=self.timeout_seconds,
            )
            ordered = sorted(response.data, key=lambda item: item.index)
            if len(ordered) != len(batch):
                raise RuntimeError(
                    "Embedding service returned an incomplete batch"
                )
            if [item.index for item in ordered] != list(range(len(batch))):
                raise RuntimeError(
                    "Embedding service returned invalid item indexes"
                )
            if any(len(item.embedding) != self.dimensions for item in ordered):
                raise RuntimeError(
                    "Embedding service returned an unexpected dimension"
                )
            embeddings.extend(list(item.embedding) for item in ordered)
        return embeddings


def cosine_similarity(
    left: Sequence[float],
    right: Sequence[float],
) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)
