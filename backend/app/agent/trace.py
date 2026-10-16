from typing import Any

from app.agent.state import AgentState


def build_rag_trace(
    *,
    query: str,
    results: list[dict[str, Any]],
    latency_ms: float,
) -> dict[str, Any]:
    method = (
        str(results[0].get("retrieval_method", "keyword"))
        if results
        else "none"
    )
    return {
        "query": query,
        "retrieval_method": method,
        "fallback_used": method == "keyword_fallback",
        "result_count": len(results),
        "latency_ms": round(latency_ms, 3),
        "results": [
            {
                key: item.get(key)
                for key in (
                    "chunk_id",
                    "title",
                    "source",
                    "score",
                    "keyword_score",
                    "vector_score",
                    "retrieval_method",
                    "citation_id",
                    "document_version",
                    "chunk_index",
                )
                if item.get(key) is not None
            }
            for item in results
        ],
    }


def build_memory_trace(
    *,
    state: AgentState,
    previous_state: AgentState | None,
    recall_latency_ms: float,
) -> dict[str, Any]:
    return {
        "previous_state_restored": previous_state is not None,
        "conversation_summary_used": bool(state.conversation_summary),
        "long_term_memory_count": len(state.long_term_memories),
        "known_entity_count": len(state.entities),
        "tool_history_count": len(state.tool_history),
        "recall_latency_ms": round(recall_latency_ms, 3),
        "context_budget": state.context_metadata.get(
            "budget_characters"
        ),
        "context_used": state.context_metadata.get(
            "used_characters"
        ),
        "dropped_memory_count": state.context_metadata.get(
            "dropped_memory_count", 0
        ),
        "dropped_knowledge_count": state.context_metadata.get(
            "dropped_knowledge_count", 0
        ),
    }
