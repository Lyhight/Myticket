from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AgentRunResponse(BaseModel):

    id: int

    ticket_id: int
    correlation_id: str | None

    classification_source: str | None

    classification_attempts: int | None

    classification_latency_ms: float | None

    classification_fallback_used: bool

    action: str | None

    action_reason: str | None

    tool_name: str | None
    tool_args: dict[str, Any] | None

    tool_result: dict[str, Any] | None

    final_reply: str | None

    review_approved: bool | None

    review_issues: list[str] | None

    state_snapshot: dict[str, Any] | None

    checkpoint_status: str | None
    rag_trace: dict[str, Any] | None
    memory_trace: dict[str, Any] | None
    context_trace: dict[str, Any] | None
    total_latency_ms: float | None
    model_provider: str | None
    model_name: str | None
    prompt_versions: dict[str, str] | None
    token_usage: dict[str, Any] | None

    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )
