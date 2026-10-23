from app.agent.state import AgentState
from app.agent.trace import build_memory_trace, build_rag_trace


def test_rag_trace_keeps_scores_but_omits_chunk_content() -> None:
    trace = build_rag_trace(
        query="退款政策",
        latency_ms=12.3456,
        results=[
            {
                "chunk_id": 3,
                "title": "退款政策",
                "source": "policy://refund",
                "content": "这是一段不应重复存入 Trace 的正文。",
                "score": 0.8,
                "keyword_score": 0.5,
                "vector_score": 1.0,
                "retrieval_method": "hybrid",
            }
        ],
    )

    assert trace["result_count"] == 1
    assert trace["retrieval_method"] == "hybrid"
    assert trace["latency_ms"] == 12.346
    assert "content" not in trace["results"][0]


def test_rag_trace_marks_keyword_fallback() -> None:
    trace = build_rag_trace(
        query="积分",
        latency_ms=1,
        results=[
            {
                "chunk_id": 1,
                "title": "积分规则",
                "source": "policy://points",
                "score": 2,
                "retrieval_method": "keyword_fallback",
            }
        ],
    )

    assert trace["fallback_used"] is True


def test_rag_trace_marks_vector_index_fallback() -> None:
    trace = build_rag_trace(
        query="退款",
        latency_ms=2,
        results=[
            {
                "chunk_id": 2,
                "title": "退款规则",
                "source": "policy://refund",
                "score": 0.9,
                "retrieval_method": "hybrid",
                "vector_backend": "local_scan_fallback",
            }
        ],
    )

    assert trace["retrieval_method"] == "hybrid"
    assert trace["vector_backend"] == "local_scan_fallback"
    assert trace["fallback_used"] is True


def test_memory_trace_reports_restored_state() -> None:
    previous = AgentState(
        ticket_id=1,
        title="订单",
        user_message="上一轮",
    )
    current = AgentState(
        ticket_id=1,
        title="订单",
        user_message="当前轮",
        conversation_summary="用户正在查询订单。",
        long_term_memories=[{"content": "用户偏好中文"}],
        entities={"order_id": "10001"},
    )

    trace = build_memory_trace(
        state=current,
        previous_state=previous,
        recall_latency_ms=2.5,
    )

    assert trace["previous_state_restored"] is True
    assert trace["conversation_summary_used"] is True
    assert trace["long_term_memory_count"] == 1
    assert trace["known_entity_count"] == 1
