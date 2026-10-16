from typing import Any, Literal

from pydantic import BaseModel, Field
TicketCategory = Literal[
    "ORDER",
    "LOGISTICS",
    "REFUND",
    "COUPON",
    "ACCOUNT",
    "PRODUCT",
    "OTHER",
]


TicketPriority = Literal[
    "LOW",
    "NORMAL",
    "HIGH",
    "URGENT",
]


TicketRoute = Literal[
    "order_support",
    "logistics_support",
    "after_sales",
    "marketing_support",
    "account_support",
    "product_support",
    "general_support",
]


class TicketClassification(BaseModel):
    category: TicketCategory
    priority: TicketPriority
    intent: str
    route_to: TicketRoute


class ClassificationExecution(BaseModel):
    classification: TicketClassification

    source: Literal[
        "qwen",
        "rule_based",
        "checkpoint",
    ]

    fallback_used: bool

    attempts: int

    latency_ms: float

class AgentAction(BaseModel):

    action: Literal[
        "tool",
        "direct_reply",
        "ask_user",
        "request_confirmation",
        "escalate_to_human",
    ]

    tool_name: str | None = Field(default=None, max_length=100)

    tool_args: dict[str, Any] = Field(
        default_factory=dict
    )

    reason: str = Field(min_length=1, max_length=2_000)

    message: str | None = Field(default=None, max_length=4_000)



class ReviewResult(BaseModel):

    approved: bool

    issues: list[str] = Field(
        default_factory=list
    )


class CustomerServiceAgentResult(BaseModel):
    classification_execution: ClassificationExecution

    action: AgentAction

    tool_result: dict[str, Any] | None = None

    reply: str

    review: ReviewResult | None = None
