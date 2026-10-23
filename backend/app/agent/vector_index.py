"""Backward-compatible imports for the pre-refactor vector module."""

from app.kb.vector_index import (
    QdrantVectorIndex,
    VectorSearchHit,
    build_vector_index,
)

__all__ = ["QdrantVectorIndex", "VectorSearchHit", "build_vector_index"]
