"""Backward-compatible imports for the pre-refactor embedding module."""

from app.kb.embeddings import DashScopeEmbeddingClient, cosine_similarity

__all__ = ["DashScopeEmbeddingClient", "cosine_similarity"]
