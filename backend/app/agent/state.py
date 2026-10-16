from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agent.schemas import (
    AgentAction,
    CustomerServiceAgentResult,
    ReviewResult,
    TicketCategory,
    TicketPriority,
    TicketRoute,
)


AgentStep = Literal[
    "received",
    "classifying",
    "extracting_entities",
    "deciding",
    "waiting_for_user",
    "waiting_for_confirmation",
    "executing_tool",
    "generating_reply",
    "reviewing",
    "waiting_for_human",
    "completed",
    "failed",
]


class ConversationTurn(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class ToolExecutionRecord(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    success: bool


class PendingAction(BaseModel):
    """等待用户明确确认后才能执行的高风险动作。"""

    tool_name: str
    tool_args: dict[str, Any] = Field(default_factory=dict)
    risk_level: Literal["medium", "high"] = "high"
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    expires_at: datetime
    confirmation_hash: str | None = None

    @staticmethod
    def fingerprint(
        *,
        tool_name: str,
        tool_args: dict[str, Any],
        summary: str,
    ) -> str:
        canonical = json.dumps(
            {
                "tool_name": tool_name,
                "tool_args": tool_args,
                "summary": summary,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def matches_confirmation(self, summary: str) -> bool:
        if not self.confirmation_hash:
            return False
        return self.confirmation_hash == self.fingerprint(
            tool_name=self.tool_name,
            tool_args=self.tool_args,
            summary=summary,
        )

    def is_expired(
        self,
        now: datetime | None = None,
    ) -> bool:
        current_time = now or datetime.now(timezone.utc)
        return current_time >= self.expires_at


class AgentState(BaseModel):
    """一轮或多轮 Agent 任务的可持久化状态。"""

    ticket_id: int | None = None
    title: str
    user_message: str
    history: list[ConversationTurn] = Field(
        default_factory=list
    )
    conversation_summary: str | None = None
    context_metadata: dict[str, Any] = Field(
        default_factory=dict
    )
    long_term_memories: list[dict[str, Any]] = Field(
        default_factory=list
    )
    retrieved_knowledge: list[dict[str, Any]] = Field(
        default_factory=list
    )

    category: TicketCategory | None = None
    priority: TicketPriority | None = None
    intent: str | None = None
    route_to: TicketRoute | None = None

    entities: dict[str, Any] = Field(
        default_factory=dict
    )
    missing_fields: list[str] = Field(
        default_factory=list
    )

    current_step: AgentStep = "received"
    action: AgentAction | None = None
    tool_history: list[ToolExecutionRecord] = Field(
        default_factory=list
    )

    requires_confirmation: bool = False
    pending_action: PendingAction | None = None
    confirmation_summary: str | None = None
    confirmed_actions: list[str] = Field(
        default_factory=list
    )

    reply: str | None = None
    review: ReviewResult | None = None
    errors: list[str] = Field(default_factory=list)

    def record_tool_execution(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        result: dict[str, Any] | None,
    ) -> None:
        success = bool(
            result and result.get("success") is True
        )

        self.tool_history.append(
            ToolExecutionRecord(
                tool_name=tool_name,
                arguments=arguments,
                result=result,
                success=success,
            )
        )

    def add_error(self, message: str) -> None:
        self.errors.append(message)
        self.current_step = "failed"

    def confirm_action(self, action_name: str) -> None:
        if action_name not in self.confirmed_actions:
            self.confirmed_actions.append(action_name)

        self.requires_confirmation = False


class AgentExecution(BaseModel):
    """兼容业务结果，同时暴露完整 Agent 状态。"""

    state: AgentState
    result: CustomerServiceAgentResult
