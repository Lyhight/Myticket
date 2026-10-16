from typing import Any

from prometheus_client import Counter, Histogram

from app.agent.schemas import CustomerServiceAgentResult


HTTP_REQUESTS = Counter(
    "myticket_http_requests_total",
    "HTTP requests handled by the API.",
    ("method", "route", "status"),
)
HTTP_DURATION = Histogram(
    "myticket_http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ("method", "route"),
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)
WORKER_TASKS = Counter(
    "myticket_worker_tasks_total",
    "Agent tasks processed by workers.",
    ("task_type", "outcome"),
)
WORKER_TASK_DURATION = Histogram(
    "myticket_worker_task_duration_seconds",
    "Agent worker task duration in seconds.",
    ("task_type",),
    buckets=(0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120),
)

AGENT_RUNS = Counter(
    "myticket_agent_runs_total",
    "Persisted Agent runs by bounded business dimensions.",
    ("category", "action", "outcome", "source"),
)
AGENT_RUN_DURATION = Histogram(
    "myticket_agent_run_duration_seconds",
    "End-to-end Agent run duration in seconds.",
    ("category", "action"),
    buckets=(0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120),
)
RAG_RETRIEVALS = Counter(
    "myticket_rag_retrievals_total",
    "RAG retrievals by bounded retrieval method and outcome.",
    ("method", "outcome"),
)
RAG_DURATION = Histogram(
    "myticket_rag_retrieval_duration_seconds",
    "RAG retrieval duration in seconds.",
    ("method",),
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
TOOL_EXECUTIONS = Counter(
    "myticket_tool_executions_total",
    "Agent tool executions by bounded tool name and outcome.",
    ("tool", "outcome"),
)

_CATEGORIES = {
    "ORDER", "LOGISTICS", "REFUND", "COUPON", "ACCOUNT", "PRODUCT", "OTHER"
}
_ACTIONS = {
    "tool", "direct_reply", "ask_user", "request_confirmation", "escalate_to_human"
}
_SOURCES = {"qwen", "rule_based", "checkpoint"}
_RAG_METHODS = {"keyword", "hybrid", "keyword_fallback", "none"}
_TOOLS = {
    "get_order",
    "get_logistics",
    "check_refund_eligibility",
    "create_refund_request",
}


def _bounded(value: Any, allowed: set[str], fallback: str = "other") -> str:
    normalized = str(value) if value is not None else fallback
    return normalized if normalized in allowed else fallback


def observe_agent_run(
    *,
    result: CustomerServiceAgentResult,
    rag_trace: dict[str, Any] | None,
    total_latency_ms: float | None,
) -> None:
    """Record only committed runs and keep every label value bounded."""
    classification = result.classification_execution.classification
    category = _bounded(classification.category, _CATEGORIES)
    action = _bounded(result.action.action, _ACTIONS)
    source = _bounded(result.classification_execution.source, _SOURCES)
    outcome = (
        "escalated"
        if action == "escalate_to_human"
        or (result.review is not None and not result.review.approved)
        else "completed"
    )
    AGENT_RUNS.labels(category, action, outcome, source).inc()
    if total_latency_ms is not None and total_latency_ms >= 0:
        AGENT_RUN_DURATION.labels(category, action).observe(total_latency_ms / 1000)

    if rag_trace is not None:
        method = _bounded(rag_trace.get("retrieval_method"), _RAG_METHODS)
        result_count = rag_trace.get("result_count", 0)
        if rag_trace.get("fallback_used"):
            rag_outcome = "fallback"
        elif isinstance(result_count, int) and result_count > 0:
            rag_outcome = "hit"
        else:
            rag_outcome = "empty"
        RAG_RETRIEVALS.labels(method, rag_outcome).inc()
        latency_ms = rag_trace.get("latency_ms")
        if isinstance(latency_ms, (int, float)) and latency_ms >= 0:
            RAG_DURATION.labels(method).observe(latency_ms / 1000)

    if action == "tool" and result.action.tool_name:
        tool = _bounded(result.action.tool_name, _TOOLS)
        success = (
            result.tool_result.get("success")
            if isinstance(result.tool_result, dict)
            else None
        )
        tool_outcome = (
            "success" if success is True else "failure" if success is False else "unknown"
        )
        TOOL_EXECUTIONS.labels(tool, tool_outcome).inc()
