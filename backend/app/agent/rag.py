"""Backward-compatible imports for the pre-refactor RAG module."""

from app.kb.chunking import KnowledgeChunker
from app.core.config import settings
from app.kb.rag import (
    HybridKnowledgeRetriever,
    KeywordKnowledgeRetriever,
    KnowledgeBaseService,
    RetrievedKnowledge,
)

__all__ = [
    "HybridKnowledgeRetriever",
    "KeywordKnowledgeRetriever",
    "KnowledgeBaseService",
    "KnowledgeChunker",
    "RetrievedKnowledge",
    "settings",
]
