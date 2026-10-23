from app.agent.langgraph_runtime import (
    LangGraphCustomerServiceRuntime as LegacyGraphRuntime,
)
from app.agent.embedding import DashScopeEmbeddingClient as LegacyEmbeddingClient
from app.agent.rag import KnowledgeChunker as LegacyKnowledgeChunker
from app.agent.tool_executor import ToolExecutor as LegacyToolExecutor
from app.agent.vector_index import QdrantVectorIndex as LegacyVectorIndex
from app.graph.runtime import LangGraphCustomerServiceRuntime
from app.kb.chunking import KnowledgeChunker
from app.kb.embeddings import DashScopeEmbeddingClient
from app.kb.vector_index import QdrantVectorIndex
from app.tools.engine import ToolExecutor


def test_legacy_graph_import_points_to_canonical_runtime() -> None:
    assert LegacyGraphRuntime is LangGraphCustomerServiceRuntime


def test_legacy_tool_import_points_to_canonical_engine() -> None:
    assert LegacyToolExecutor is ToolExecutor


def test_legacy_chunker_import_points_to_kb_capability() -> None:
    assert LegacyKnowledgeChunker is KnowledgeChunker


def test_legacy_embedding_import_points_to_kb_capability() -> None:
    assert LegacyEmbeddingClient is DashScopeEmbeddingClient


def test_legacy_vector_import_points_to_kb_capability() -> None:
    assert LegacyVectorIndex is QdrantVectorIndex
